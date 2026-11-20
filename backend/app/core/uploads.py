"""엑셀/CSV 업로드 공통 처리.

- .xlsx / .csv 지원 (.xls 와 비밀번호 걸린 파일은 안내 메시지)
- 1행이 헤더가 아닌 파일(택배사·오픈마켓 파일은 위에 제목 줄이 있는 경우가 많음)을 위해
  위쪽 15줄 중 '아는 열 이름'이 가장 많이 들어 있는 줄을 헤더로 고른다.
- 미리보기 → 확인 2단계 처리를 위해 업로드 결과를 30분간 메모리에 보관한다.
"""

from __future__ import annotations

import csv
import io
import re
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass
from typing import Any

from .errors import NotFoundError, ValidationFailed

OLE_MAGIC = b"\xd0\xcf\x11\xe0"
MAX_UPLOAD = 10 * 1024 * 1024


def _norm(h: Any) -> str:
    return re.sub(r"[\s_\-()（）\[\]/·.]", "", str(h or "")).lower()


@dataclass
class Table:
    headers: list[str]
    rows: list[dict[str, Any]]  # 헤더 텍스트 -> 값
    header_row: int  # 1부터


def read_rows(filename: str, data: bytes) -> list[list[Any]]:
    if not data:
        raise ValidationFailed("빈 파일이에요.")
    if len(data) > MAX_UPLOAD:
        raise ValidationFailed("파일이 너무 커요 (10MB 이하).")
    name = (filename or "").lower()
    if data[:4] == OLE_MAGIC:
        raise ValidationFailed(
            "비밀번호가 걸린 엑셀이거나 옛날 .xls 파일이에요. 엑셀에서 열어 비밀번호를 풀고 "
            "'다른 이름으로 저장 → Excel 통합 문서(.xlsx)' 로 저장한 뒤 다시 올려 주세요."
        )
    if name.endswith(".csv") or not data[:2] == b"PK":
        for enc in ("utf-8-sig", "cp949", "euc-kr"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValidationFailed("파일 글자를 읽지 못했어요. .xlsx 로 저장해서 올려 주세요.")
        return [row for row in csv.reader(io.StringIO(text))]
    try:
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError) as e:
        raise ValidationFailed("엑셀 파일을 열지 못했어요. .xlsx 로 다시 저장해서 올려 주세요.") from e
    ws = wb.worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return rows


def find_table(rows: list[list[Any]], hints: dict[str, list[str]], min_hits: int = 2) -> Table:
    """hints: {필드: [후보 헤더...]} — 후보와 정규화 일치하는 칸이 가장 많은 줄을 헤더로."""
    norm_hints = {f: [_norm(h) for h in hs] for f, hs in hints.items()}
    best_idx, best_hits = -1, 0
    for i, row in enumerate(rows[:15]):
        cells = {_norm(c) for c in row if c not in (None, "")}
        hits = sum(1 for hs in norm_hints.values() if any(h in cells for h in hs))
        if hits > best_hits:
            best_idx, best_hits = i, hits
    if best_idx < 0 or best_hits < min_hits:
        raise ValidationFailed("열 이름(헤더)을 찾지 못했어요. 택배사/오픈마켓에서 받은 원본 파일을 그대로 올려 주세요.")
    headers = [str(c).strip() if c not in (None, "") else f"열{j + 1}" for j, c in enumerate(rows[best_idx])]
    out: list[dict[str, Any]] = []
    for row in rows[best_idx + 1 :]:
        if not any(c not in (None, "") for c in row):
            continue
        out.append({headers[j]: (row[j] if j < len(row) else None) for j in range(len(headers))})
    return Table(headers=headers, rows=out, header_row=best_idx + 1)


def pick(row: dict[str, Any], candidates: list[str]) -> Any:
    """후보 헤더 중 처음으로 값이 있는 칸 (정규화 비교)."""
    by_norm = {_norm(k): v for k, v in row.items()}
    for c in candidates:
        v = by_norm.get(_norm(c))
        if v not in (None, ""):
            return v
    return None


def cell_text(v: Any) -> str:
    """엑셀 숫자 칸(송장번호 등)이 1.23E+11 이나 123.0 으로 오는 것을 정리."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


class PreviewStore:
    def __init__(self, ttl_sec: int = 1800):
        self.ttl = ttl_sec
        self._items: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def put(self, value: Any) -> str:
        key = uuid.uuid4().hex[:12]
        with self._lock:
            self._gc()
            self._items[key] = (time.monotonic(), value)
        return key

    def get(self, key: str) -> Any:
        with self._lock:
            self._gc()
            hit = self._items.get(key)
        if hit is None:
            raise NotFoundError("미리보기가 만료됐어요. 파일을 다시 올려 주세요.")
        return hit[1]

    def pop(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def _gc(self) -> None:
        t = time.monotonic()
        for k in [k for k, (ts, _) in self._items.items() if t - ts > self.ttl]:
            self._items.pop(k, None)
