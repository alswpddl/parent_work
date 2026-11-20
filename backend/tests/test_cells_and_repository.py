from __future__ import annotations

from datetime import date

import pytest

from app.core.cells import from_cell, to_cell
from app.core.errors import ConflictError, SchemaError
from app.core.repository import Repository
from app.core.sheet_schema import CUSTOMERS, ORDERS
from app.core.sheets import MemoryBackend, SheetsClient


# ---------------------------------------------------------------- 셀 변환
def test_phone_and_zip_keep_leading_zero():
    assert to_cell("str", "010-1234-5678") == "010-1234-5678"
    assert to_cell("str", "01234") == "01234"
    assert from_cell("str", "01234") == "01234"


def test_date_roundtrip_and_sheet_serial():
    assert to_cell("date", date(2026, 11, 20)) == "2026-11-20"
    assert from_cell("date", "2026-11-20") == date(2026, 11, 20)
    assert from_cell("date", "2026. 11. 20") == date(2026, 11, 20)
    assert from_cell("date", 46346) == date(2026, 11, 20)  # 시트 날짜 일련번호


def test_numbers_and_bools():
    assert from_cell("int", "1,200") == 1200
    assert from_cell("float", 1.9) == 1.9
    assert from_cell("bool", "TRUE") is True
    assert from_cell("bool", "") is None
    assert from_cell("str", 12.0) == "12"


# ---------------------------------------------------------------- 저장소
@pytest.fixture
def sheets():
    b = MemoryBackend()
    c = SheetsClient(b, ttl=0)
    c.ensure_tab(CUSTOMERS)
    return b, c


def test_ensure_tab_adds_only_missing_headers():
    b = MemoryBackend()
    b.tabs["거래처"] = [["거래처명", "거래처ID", "부모님메모"]]
    added = b.ensure_tab("거래처", CUSTOMERS.headers, [])
    assert "거래처명" not in added and "연락처" in added
    assert b.tabs["거래처"][0][:3] == ["거래처명", "거래처ID", "부모님메모"]  # 기존 순서·추가 열 유지


def test_reordered_columns_and_parent_column_preserved(sheets):
    b, c = sheets
    # 부모님이 열 순서를 바꾸고 '부모님메모' 열을 추가한 상황
    header = b.tabs["거래처"][0]
    header.reverse()
    header.append("부모님메모")
    repo = Repository(c, CUSTOMERS)
    repo.insert({"customer_id": "C0001", "name": "한솥식당", "phone": "010-1111-2222", "active": True})
    row = b.tabs["거래처"][1]
    row[header.index("부모님메모")] = "=SUM(1,2)"  # 수식 직접 입력

    repo.update(("C0001",), {"phone": "010-9999-8888"})
    row = b.tabs["거래처"][1]
    assert row[header.index("연락처")] == "010-9999-8888"
    assert row[header.index("부모님메모")] == "=SUM(1,2)"  # 덮어쓰지 않음
    assert repo.get("C0001")["name"] == "한솥식당"


def test_update_finds_row_even_after_sort(sheets):
    b, c = sheets
    repo = Repository(c, CUSTOMERS)
    repo.insert_many([{"customer_id": "C0001", "name": "가"}, {"customer_id": "C0002", "name": "나"}])
    # 부모님이 시트를 정렬해서 행 순서가 바뀜
    b.tabs["거래처"][1], b.tabs["거래처"][2] = b.tabs["거래처"][2], b.tabs["거래처"][1]
    repo.update(("C0001",), {"memo": "확인"})
    assert repo.get("C0001")["memo"] == "확인"
    assert repo.get("C0002")["memo"] == ""


def test_update_missing_row_raises_conflict(sheets):
    _, c = sheets
    repo = Repository(c, CUSTOMERS)
    with pytest.raises(ConflictError):
        repo.update(("C9999",), {"memo": "x"})


def test_missing_key_header_is_schema_error():
    b = MemoryBackend()
    b.tabs["주문장"] = [["거래처명"]]
    repo = Repository(SheetsClient(b, ttl=0), ORDERS)
    with pytest.raises(SchemaError):
        repo.all()


def test_only_changed_cells_are_written(sheets):
    b, c = sheets
    repo = Repository(c, CUSTOMERS)
    repo.insert({"customer_id": "C0001", "name": "한솥식당", "address": "서울"})
    writes_before = b.calls["write"]
    repo.update(("C0001",), {"memo": "a", "address": "부산"})
    assert b.calls["write"] == writes_before + 1  # 한 번의 batch 쓰기


def test_cache_reduces_reads():
    b = MemoryBackend()
    c = SheetsClient(b, ttl=60)
    c.ensure_tab(CUSTOMERS)
    repo = Repository(c, CUSTOMERS)
    repo.all()
    repo.all()
    repo.all()
    assert b.calls["read"] == 1
