"""시트 1개 = Repository 1개.

- 헤더 텍스트로 열 위치를 찾으므로 부모님이 열 순서를 바꿔도 동작한다.
- 업데이트는 '바뀐 칸만' 쓴다. 부모님이 추가한 수식·메모 열은 절대 덮어쓰지 않는다.
- 업데이트·삭제 직전에는 캐시를 무시하고 새로 읽은 뒤 기본키로 행을 다시 찾는다.
  (그 사이 부모님이 시트를 정렬해도 엉뚱한 행을 고치지 않게)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Generic, Iterable, TypeVar

from .cells import from_cell, to_cell
from .errors import ConflictError, SchemaError
from .sheet_schema import TabSpec
from .sheets import CellRun, SheetsClient

log = logging.getLogger(__name__)

Key = tuple[Any, ...]


@dataclass
class Record:
    data: dict[str, Any]
    row: int  # 시트 행 번호(1부터, 헤더=1)


T = TypeVar("T")


class Repository(Generic[T]):
    spec: TabSpec

    def __init__(self, sheets: SheetsClient, spec: TabSpec | None = None):
        self.sheets = sheets
        if spec is not None:
            self.spec = spec
        self._warned_missing: set[str] = set()

    # ------------------------------------------------------------------ 내부
    def _colmap(self, header_row: list[Any]) -> dict[str, int]:
        pos: dict[str, int] = {}
        for i, h in enumerate(header_row):
            text = str(h).strip()
            if text and text not in pos:
                pos[text] = i
        out: dict[str, int] = {}
        for c in self.spec.columns:
            if c.header in pos:
                out[c.key] = pos[c.header]
            elif c.key not in self._warned_missing:
                self._warned_missing.add(c.key)
                log.warning("[%s] 헤더 '%s' 열이 없어요 (서버 재시작 시 자동 추가됨)", self.spec.title, c.header)
        for k in self.spec.key_fields:
            if k not in out:
                raise SchemaError(f"'{self.spec.title}' 탭에 '{self.spec.column(k).header}' 열이 꼭 있어야 해요.")
        return out

    def _parse(self, row: list[Any], colmap: dict[str, int]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for c in self.spec.columns:
            idx = colmap.get(c.key)
            raw = row[idx] if idx is not None and idx < len(row) else None
            data[c.key] = from_cell(c.type, raw)
        return data

    def key_of(self, data: dict[str, Any]) -> Key:
        out = []
        for k in self.spec.key_fields:
            v = data.get(k)
            col = self.spec.column(k)
            # 키 비교는 셀 표현 기준으로 정규화 (int 1 == '1')
            out.append(to_cell(col.type, v) if v is not None else "")
        return tuple(out)

    def _read(self, fresh: bool) -> tuple[dict[str, int], list[Record], int]:
        values = self.sheets.read(self.spec.title, fresh=fresh)
        if not values:
            raise SchemaError(f"'{self.spec.title}' 탭에 헤더가 없어요.")
        header = values[0]
        colmap = self._colmap(header)
        records: list[Record] = []
        for i, row in enumerate(values[1:], start=2):
            if not any(str(v).strip() for v in row if v is not None):
                continue
            records.append(Record(self._parse(row, colmap), i))
        return colmap, records, len(header)

    # ------------------------------------------------------------------ 읽기
    def all(self, fresh: bool = False) -> list[Record]:
        return self._read(fresh)[1]

    def rows(self, fresh: bool = False) -> list[dict[str, Any]]:
        return [r.data for r in self.all(fresh)]

    def find(self, pred: Callable[[dict[str, Any]], bool], fresh: bool = False) -> list[dict[str, Any]]:
        return [r.data for r in self.all(fresh) if pred(r.data)]

    def get(self, *key: Any, fresh: bool = False) -> dict[str, Any] | None:
        target = self.key_of(dict(zip(self.spec.key_fields, key)))
        for r in self.all(fresh):
            if self.key_of(r.data) == target:
                return r.data
        return None

    # ------------------------------------------------------------------ 쓰기
    def insert_many(self, items: Iterable[dict[str, Any]]) -> None:
        items = list(items)
        if not items:
            return
        with self.sheets.lock:
            values = self.sheets.read(self.spec.title)
            header = values[0] if values else self.spec.headers
            colmap = self._colmap(header)
            width = len(header)
            rows = []
            for item in items:
                row: list[Any] = [""] * width
                for c in self.spec.columns:
                    idx = colmap.get(c.key)
                    if idx is not None and c.key in item:
                        row[idx] = to_cell(c.type, item[c.key])
                rows.append(row)
            self.sheets.append(self.spec.title, rows)

    def insert(self, item: dict[str, Any]) -> None:
        self.insert_many([item])

    def update_many(self, changes: list[tuple[Key, dict[str, Any]]]) -> None:
        """changes: [(기본키 튜플, {바꿀 key: 값})]. 바뀐 칸만 쓴다."""
        if not changes:
            return
        with self.sheets.lock:
            colmap, records, _ = self._read(fresh=True)
            index = {self.key_of(r.data): r.row for r in records}
            runs: list[CellRun] = []
            for key, ch in changes:
                norm_key = self.key_of(dict(zip(self.spec.key_fields, key)))
                row_no = index.get(norm_key)
                if row_no is None:
                    raise ConflictError("고치려는 줄이 시트에서 사라졌어요. 새로고침 후 다시 해 주세요.")
                cells: dict[int, Any] = {}
                for k, v in ch.items():
                    if k not in colmap:
                        continue
                    cells[colmap[k]] = to_cell(self.spec.column(k).type, v)
                runs.extend(_to_runs(row_no, cells))
            self.sheets.update_runs(self.spec.title, runs)

    def update(self, key: Key, changes: dict[str, Any]) -> None:
        self.update_many([(key, changes)])

    def delete_many(self, keys: Iterable[Key]) -> None:
        keys = list(keys)
        if not keys:
            return
        with self.sheets.lock:
            _, records, _ = self._read(fresh=True)
            index = {self.key_of(r.data): r.row for r in records}
            rows = []
            for key in keys:
                norm = self.key_of(dict(zip(self.spec.key_fields, key)))
                if norm in index:
                    rows.append(index[norm])
            self.sheets.delete_rows(self.spec.title, rows)


def _to_runs(row_no: int, cells: dict[int, Any]) -> list[CellRun]:
    """{0-based 열 인덱스: 값} -> 연속 구간별 CellRun"""
    runs: list[CellRun] = []
    for idx in sorted(cells):
        if runs and runs[-1].col + len(runs[-1].values) - 1 == idx:  # 바로 옆 칸이면 이어 붙임
            runs[-1].values.append(cells[idx])
        else:
            runs.append(CellRun(row=row_no, col=idx + 1, values=[cells[idx]]))
    return runs
