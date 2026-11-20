"""Google Sheets 접근 계층.

구성
- SheetBackend: 실제 저장소 인터페이스 (gspread / 메모리)
- SheetsClient: 탭 단위 캐시 + 잠금 + 쓰기 후 캐시 무효화

Sheets API 쿼터(사용자당 분당 읽기 60 / 쓰기 60)를 지키기 위한 원칙
- 탭 전체를 한 번에 읽는다(요청 1회) → TTL 캐시
- 여러 셀 쓰기는 values.batchUpdate 한 번으로 묶는다
- 429/5xx 는 지수 백오프로 재시도
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

from .errors import UpstreamError
from .sheet_schema import TabSpec

log = logging.getLogger(__name__)


@dataclass
class CellRun:
    """한 행에서 연속된 열 묶음 쓰기. col 은 1부터 시작."""

    row: int
    col: int
    values: list[Any]


class SheetBackend(Protocol):
    name: str

    def list_tabs(self) -> list[str]: ...

    def get_values(self, title: str) -> list[list[Any]]: ...

    def append_rows(self, title: str, rows: list[list[Any]]) -> None: ...

    def update_runs(self, title: str, runs: list[CellRun]) -> None: ...

    def delete_rows(self, title: str, row_numbers: list[int]) -> None: ...

    def ensure_tab(self, title: str, headers: list[str], text_headers: list[str]) -> list[str]:
        """탭이 없으면 만들고, 있으면 빠진 헤더를 오른쪽 끝에 추가한다. 추가된 헤더 목록을 돌려준다."""
        ...


def col_letter(n: int) -> str:
    """1 -> A, 27 -> AA"""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _quote(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# 메모리 백엔드 — 테스트와 Codespaces 첫 실행(구글 계정 연결 전)용
# ---------------------------------------------------------------------------
class MemoryBackend:
    name = "memory"

    def __init__(self) -> None:
        self.tabs: dict[str, list[list[Any]]] = {}
        self.calls: dict[str, int] = {"read": 0, "write": 0}

    def list_tabs(self) -> list[str]:
        return list(self.tabs)

    def get_values(self, title: str) -> list[list[Any]]:
        self.calls["read"] += 1
        rows = self.tabs.get(title)
        if rows is None:
            raise UpstreamError(f"시트 탭 '{title}' 이(가) 없어요.")
        width = max((len(r) for r in rows), default=0)
        return [list(r) + [""] * (width - len(r)) for r in rows]

    def append_rows(self, title: str, rows: list[list[Any]]) -> None:
        self.calls["write"] += 1
        self.tabs.setdefault(title, []).extend([list(r) for r in rows])

    def update_runs(self, title: str, runs: list[CellRun]) -> None:
        self.calls["write"] += 1
        sheet = self.tabs[title]
        for run in runs:
            while len(sheet) < run.row:
                sheet.append([])
            row = sheet[run.row - 1]
            end = run.col - 1 + len(run.values)
            if len(row) < end:
                row.extend([""] * (end - len(row)))
            row[run.col - 1 : end] = run.values

    def delete_rows(self, title: str, row_numbers: list[int]) -> None:
        self.calls["write"] += 1
        sheet = self.tabs[title]
        for r in sorted(set(row_numbers), reverse=True):
            if 1 < r <= len(sheet):  # 헤더(1행)는 지우지 않음
                del sheet[r - 1]

    def ensure_tab(self, title: str, headers: list[str], text_headers: list[str]) -> list[str]:
        if title not in self.tabs or not self.tabs[title]:
            self.tabs[title] = [list(headers)]
            return list(headers)
        header_row = self.tabs[title][0]
        existing = {str(h).strip() for h in header_row}
        missing = [h for h in headers if h not in existing]
        header_row.extend(missing)
        return missing


# ---------------------------------------------------------------------------
# gspread 백엔드 — 실제 Google Sheets
# ---------------------------------------------------------------------------
class GspreadBackend:
    """gspread 의 저수준 values_* / batch_update 만 사용해 버전 차이에 덜 민감하게 만든다."""

    name = "gspread"
    RETRY_STATUS = {429, 500, 502, 503, 504}

    def __init__(self, spreadsheet_id: str, service_account_info: dict, max_retries: int = 5):
        try:
            import gspread  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("gspread 가 설치되어 있지 않아요. pip install -r requirements.txt") from e
        self._gspread = gspread
        self._max_retries = max_retries
        gc = gspread.service_account_from_dict(service_account_info)
        self._sh = self._call(gc.open_by_key, spreadsheet_id)
        self._sheet_ids: dict[str, int] = {}

    # --- 재시도 ---
    def _call(self, fn, *args, **kwargs):
        delay = 1.0
        for attempt in range(self._max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except self._gspread.exceptions.APIError as e:  # type: ignore[attr-defined]
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in self.RETRY_STATUS and attempt < self._max_retries:
                    wait = delay + random.uniform(0, 0.5)
                    log.warning("Sheets API %s, %.1fs 후 재시도 (%d/%d)", status, wait, attempt + 1, self._max_retries)
                    time.sleep(wait)
                    delay = min(delay * 2, 32)
                    continue
                raise UpstreamError("구글 시트 연결이 잠시 불안정해요. 다시 눌러 주세요.") from e

    def _sheet_id(self, title: str) -> int:
        if title not in self._sheet_ids:
            for ws in self._call(self._sh.worksheets):
                self._sheet_ids[ws.title] = ws.id
        if title not in self._sheet_ids:
            raise UpstreamError(f"시트 탭 '{title}' 이(가) 없어요.")
        return self._sheet_ids[title]

    def list_tabs(self) -> list[str]:
        wss = self._call(self._sh.worksheets)
        self._sheet_ids = {ws.title: ws.id for ws in wss}
        return list(self._sheet_ids)

    def get_values(self, title: str) -> list[list[Any]]:
        res = self._call(
            self._sh.values_get,
            _quote(title),
            params={"valueRenderOption": "UNFORMATTED_VALUE", "dateTimeRenderOption": "FORMATTED_STRING"},
        )
        rows = res.get("values", [])
        width = max((len(r) for r in rows), default=0)
        return [list(r) + [""] * (width - len(r)) for r in rows]

    def append_rows(self, title: str, rows: list[list[Any]]) -> None:
        if not rows:
            return
        self._call(
            self._sh.values_append,
            f"{_quote(title)}!A1",
            params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
            body={"values": rows},
        )

    def update_runs(self, title: str, runs: list[CellRun]) -> None:
        if not runs:
            return
        data = []
        for run in runs:
            start = f"{col_letter(run.col)}{run.row}"
            end = f"{col_letter(run.col + len(run.values) - 1)}{run.row}"
            data.append({"range": f"{_quote(title)}!{start}:{end}", "values": [run.values]})
        self._call(self._sh.values_batch_update, body={"valueInputOption": "RAW", "data": data})

    def delete_rows(self, title: str, row_numbers: list[int]) -> None:
        rows = sorted({r for r in row_numbers if r > 1}, reverse=True)
        if not rows:
            return
        sid = self._sheet_id(title)
        requests = [
            {"deleteDimension": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": r - 1, "endIndex": r}}}
            for r in rows
        ]
        self._call(self._sh.batch_update, {"requests": requests})

    def ensure_tab(self, title: str, headers: list[str], text_headers: list[str]) -> list[str]:
        tabs = self.list_tabs()
        if title not in tabs:
            ws = self._call(self._sh.add_worksheet, title=title, rows=1000, cols=max(26, len(headers)))
            self._sheet_ids[title] = ws.id
            current: list[str] = []
        else:
            res = self._call(self._sh.values_get, f"{_quote(title)}!1:1")
            current = [str(h).strip() for h in (res.get("values") or [[]])[0]]

        existing = set(current)
        missing = [h for h in headers if h not in existing]
        if missing:
            sid = self._sheet_ids[title]
            start_col = len(current) + 1
            needed_cols = len(current) + len(missing)
            # 열이 모자라면 늘린다
            props = self._call(self._sh.fetch_sheet_metadata)
            col_count = next(
                s["properties"]["gridProperties"]["columnCount"]
                for s in props["sheets"]
                if s["properties"]["sheetId"] == sid
            )
            if col_count < needed_cols:
                self._call(
                    self._sh.batch_update,
                    {"requests": [{"appendDimension": {"sheetId": sid, "dimension": "COLUMNS", "length": needed_cols - col_count}}]},
                )
            self.update_runs(title, [CellRun(row=1, col=start_col, values=missing)])
            current = current + missing

        self._apply_formats(title, current, text_headers)
        return missing

    def _apply_formats(self, title: str, header_row: list[str], text_headers: list[str]) -> None:
        sid = self._sheet_ids[title]
        requests: list[dict] = [
            {  # 1행 고정
                "updateSheetProperties": {
                    "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            {  # 헤더 굵게 + 연한 배경
                "repeatCell": {
                    "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {"red": 0.89, "green": 0.94, "blue": 0.91},
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            },
        ]
        for h in text_headers:
            if h in header_row:
                idx = header_row.index(h)
                requests.append(
                    {
                        "repeatCell": {
                            "range": {"sheetId": sid, "startRowIndex": 1, "startColumnIndex": idx, "endColumnIndex": idx + 1},
                            "cell": {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}},
                            "fields": "userEnteredFormat.numberFormat",
                        }
                    }
                )
        self._call(self._sh.batch_update, {"requests": requests})


# ---------------------------------------------------------------------------
# 캐시 + 잠금 클라이언트
# ---------------------------------------------------------------------------
class SheetsClient:
    def __init__(self, backend: SheetBackend, ttl: float = 30.0):
        self.backend = backend
        self.ttl = ttl
        self.lock = threading.RLock()  # 읽고-고치고-쓰기를 한 덩어리로 묶을 때 사용
        self._cache: dict[str, tuple[float, list[list[Any]]]] = {}

    def read(self, title: str, fresh: bool = False) -> list[list[Any]]:
        with self.lock:
            hit = self._cache.get(title)
            if not fresh and hit is not None and (time.monotonic() - hit[0]) < self.ttl:
                return [list(r) for r in hit[1]]
            values = self.backend.get_values(title)
            self._cache[title] = (time.monotonic(), values)
            return [list(r) for r in values]

    def append(self, title: str, rows: list[list[Any]]) -> None:
        with self.lock:
            self.backend.append_rows(title, rows)
            self.invalidate(title)

    def update_runs(self, title: str, runs: list[CellRun]) -> None:
        with self.lock:
            self.backend.update_runs(title, runs)
            self.invalidate(title)

    def delete_rows(self, title: str, row_numbers: list[int]) -> None:
        with self.lock:
            self.backend.delete_rows(title, row_numbers)
            self.invalidate(title)

    def ensure_tab(self, spec: TabSpec) -> list[str]:
        with self.lock:
            added = self.backend.ensure_tab(spec.title, spec.headers, spec.text_headers)
            self.invalidate(spec.title)
            return added

    def invalidate(self, title: str | None = None) -> None:
        if title is None:
            self._cache.clear()
        else:
            self._cache.pop(title, None)


def build_backend(config) -> SheetBackend:
    if config.sheets_backend == "gspread":
        if not config.spreadsheet_id or not config.service_account_info:
            raise RuntimeError("GOOGLE_SPREADSHEET_ID 와 GOOGLE_SERVICE_ACCOUNT_JSON 을 설정해 주세요.")
        return GspreadBackend(config.spreadsheet_id, config.service_account_info)
    return MemoryBackend()
