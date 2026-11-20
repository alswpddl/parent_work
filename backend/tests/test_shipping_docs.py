from __future__ import annotations

from datetime import date
from io import BytesIO

from openpyxl import load_workbook

from app.modules.q1_shipping.carriers import CARRIERS, get_format
from app.modules.q1_shipping.dispatch_text import build_dispatch_text
from app.modules.q1_shipping.parcel_excel import build_parcel_workbook
from app.schemas.order import OrderCreate, OrderItemIn


def _order(ctx, items, **kw):
    return ctx.orders.create(OrderCreate(items=[OrderItemIn(sku=s, qty=q) for s, q in items], **kw))


def test_parcel_excel_generic(ctx):
    o = _order(ctx, [("SES-18L", 7), ("CHI-5KG", 1)], customer_id="C0001", note="오전 배송")
    data = build_parcel_workbook([o], get_format("generic"), ctx.settings.load())
    ws = load_workbook(BytesIO(data)).active
    headers = [c.value for c in ws[1]]
    row = {h: c for h, c in zip(headers, ws[2])}
    assert row["받는분"].value == "김사장"
    assert row["받는분 전화"].value == "010-1234-5678" and row["받는분 전화"].number_format == "@"
    assert row["받는분 우편번호"].value == "01234"  # 앞자리 0 유지
    assert row["박스수량"].value == 2 + 1  # 참기름 7통(6입) → 2박스, 고춧가루 1봉 → 1박스
    assert "참기름 1.8L x7" in row["품목명"].value
    assert row["보내는분"].value == "예시공장"


def test_all_carrier_formats_build(ctx):
    o = _order(ctx, [("SES-18L", 1)], customer_id="C0001")
    for code, fmt in CARRIERS.items():
        data = build_parcel_workbook([o], fmt, ctx.settings.load())
        ws = load_workbook(BytesIO(data)).active
        assert ws.max_row == 2, code
    assert get_format("없는코드").code == "generic"


def test_dispatch_text(ctx):
    o = _order(ctx, [("CHI-10KG", 70)], customer_id="C0002", due_date=date(2026, 11, 20), note="지게차 있음")
    text = build_dispatch_text(o, ctx.settings.load())
    assert text.startswith("[화물 배차 요청]")
    assert "상차지: 경기도 OO시 OO로 123 / 예시공장" in text
    assert "하차지: 경기도 OO시 OO길 7 물류창고" in text
    assert "총 중량: 약 721kg / 파레트 2개" in text
    assert "도착 희망: 11/20(금)" in text
    assert "특이사항: 지게차 있음" in text
