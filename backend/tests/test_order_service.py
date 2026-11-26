from __future__ import annotations

from datetime import date

import pytest

from app.core.errors import ValidationFailed
from app.modules.q1_orders.parser import parse_with_rules
from app.schemas.order import OrderCreate, OrderItemIn, OrderPatch
from app.services.order_service import ParsedItem, ParsedOrder
from app.services.shipping_rule import box_count, decide_method, pallet_count
from app.schemas.settings import AppSettings

from .conftest import BASE_DAY
from .test_parser_and_matching import SAMPLE


def _create(ctx, items, **kw):
    return ctx.orders.create(OrderCreate(items=[OrderItemIn(sku=s, qty=q) for s, q in items], **kw))


# ---------------------------------------------------------------- 분기 규칙
def test_decide_method_priority():
    st = AppSettings(threshold_kg=50)
    assert decide_method(49.9, st) == ("택배", "자동")
    assert decide_method(50, st) == ("화물", "자동")
    assert decide_method(10, st, customer_default="화물") == ("화물", "거래처기본")
    assert decide_method(500, st, manual="택배", customer_default="화물") == ("택배", "수동")
    assert pallet_count(1300, AppSettings(pallet_kg=600)) == 3
    assert pallet_count(0, st) == 0


def test_box_count(ctx):
    pm = ctx.products.map()
    assert box_count([(10, pm["SES-18L"]), (3, pm["CHI-5KG"])]) == 2 + 2


# ---------------------------------------------------------------- 초안
def test_draft_from_sample(ctx):
    parsed = parse_with_rules(SAMPLE, ctx.customers.list(), ctx.products.list(), BASE_DAY)
    d = ctx.orders.build_draft(parsed, parser="rule", warnings=[], raw_text=SAMPLE)
    assert d.customer.matched and d.customer.customer_id == "C0001"
    assert d.address.startswith("서울시")  # 거래처 기본 배송지로 채움
    assert d.order_kg == pytest.approx(10 * 1.9 + 5 * 1.9 + 2 * 5.2)  # 38.9kg
    assert d.ship_method == "택배" and d.method_by == "자동"
    assert d.warnings == []


def test_draft_unknown_item_and_customer_warn(ctx):
    parsed = ParsedOrder(customer_name="새로운식당", items=[ParsedItem(raw_name="참깨 1kg", qty=3)])
    d = ctx.orders.build_draft(parsed, parser="ai", warnings=[], raw_text="")
    assert not d.customer.matched
    assert d.items[0].sku is None
    assert len(d.warnings) == 2


# ---------------------------------------------------------------- 생성
def test_create_writes_one_row_per_line(ctx, backend, events):
    o = _create(ctx, [("SES-18L", 10), ("CHI-5KG", 2)], customer_id="C0001", due_date=date(2026, 11, 20))
    import re

    assert re.fullmatch(r"\d{8}-[2-9A-HJKMNP-Z]{4}", o.order_id)
    assert [l.line_no for l in o.lines] == [1, 2]
    assert o.recipient == "김사장" and o.phone == "010-1234-5678"
    assert o.total_amount == 10 * 38000 + 2 * 95000
    sheet = backend.tabs["주문장"]
    assert len(sheet) == 3  # 헤더 + 2줄
    header = sheet[0]
    assert sheet[1][header.index("연락처")] == "010-1234-5678"
    assert sheet[1][header.index("납기일")] == "2026-11-20"
    assert sheet[2][header.index("원문")] == ""  # 원문은 첫 줄에만
    assert events[0][0] == "order.created"

    o2 = _create(ctx, [("PER-18L", 1)], customer_id="C0001")
    assert o2.order_id != o.order_id and o2.order_id[:8] == o.order_id[:8]


def test_customer_default_truck(ctx):
    o = _create(ctx, [("SES-18L", 1)], customer_id="C0002")  # 행복마트: 기본출고방식 화물
    assert o.ship_method == "화물" and o.method_by == "거래처기본"


def test_heavy_order_goes_to_truck_and_manual_override(ctx):
    o = _create(ctx, [("CHI-10KG", 6)], customer_id="C0001")  # 61.8kg
    assert o.ship_method == "화물" and o.method_by == "자동"
    o = _create(ctx, [("CHI-10KG", 6)], customer_id="C0001", ship_method="택배")
    assert o.ship_method == "택배" and o.method_by == "수동"


def test_create_rejects_unknown_sku_and_missing_customer(ctx):
    with pytest.raises(ValidationFailed):
        _create(ctx, [("NOPE", 1)], customer_id="C0001")
    with pytest.raises(ValidationFailed):
        _create(ctx, [("SES-18L", 1)])


def test_duplicate_items_are_merged(ctx):
    o = _create(ctx, [("SES-18L", 2), ("SES-18L", 3)], customer_id="C0001")
    assert len(o.lines) == 1 and o.lines[0].qty == 5


# ---------------------------------------------------------------- 수정
def test_update_items_add_remove_and_reclassify(ctx, backend, events):
    o = _create(ctx, [("SES-18L", 2), ("PER-18L", 2)], customer_id="C0001")
    assert o.ship_method == "택배"
    # 2줄 → 3줄 (고춧가루 10kg 5개 추가로 무게 초과 → 자동 화물)
    o = ctx.orders.update(
        o.order_id,
        OrderPatch(items=[OrderItemIn(sku="SES-18L", qty=4), OrderItemIn(sku="PER-18L", qty=2), OrderItemIn(sku="CHI-10KG", qty=5)]),
    )
    assert [(l.sku, l.qty) for l in o.lines] == [("SES-18L", 4), ("PER-18L", 2), ("CHI-10KG", 5)]
    assert o.ship_method == "화물"
    # 3줄 → 1줄
    o = ctx.orders.update(o.order_id, OrderPatch(items=[OrderItemIn(sku="PER-18L", qty=1)]))
    assert [(l.sku, l.qty) for l in o.lines] == [("PER-18L", 1)]
    assert o.ship_method == "택배"
    assert len([r for r in backend.tabs["주문장"][1:] if r[0] == o.order_id]) == 1
    assert events[-1][0] == "order.updated"


def test_manual_method_is_kept_until_auto_requested(ctx):
    o = _create(ctx, [("SES-18L", 1)], customer_id="C0001", ship_method="화물")
    o = ctx.orders.update(o.order_id, OrderPatch(items=[OrderItemIn(sku="SES-18L", qty=2)]))
    assert o.ship_method == "화물" and o.method_by == "수동"
    o = ctx.orders.update(o.order_id, OrderPatch(auto_method=True))
    assert o.ship_method == "택배" and o.method_by == "자동"


def test_header_fields_written_to_all_lines(ctx, backend):
    o = _create(ctx, [("SES-18L", 1), ("PER-18L", 1)], customer_id="C0001")
    ctx.orders.update(o.order_id, OrderPatch(address="부산시 해운대구 우동 1", note="문 앞"))
    header = backend.tabs["주문장"][0]
    rows = [r for r in backend.tabs["주문장"][1:] if r[0] == o.order_id]
    assert {r[header.index("배송지")] for r in rows} == {"부산시 해운대구 우동 1"}


# ---------------------------------------------------------------- 출고 / 취소
def test_ship_unship_cancel_flow(ctx, events):
    o = _create(ctx, [("SES-18L", 1)], customer_id="C0001")
    o = ctx.orders.ship(o.order_id)
    assert o.status == "출고완료" and o.shipped_at is not None
    assert ctx.orders.ship(o.order_id).status == "출고완료"  # 두 번 눌러도 안전
    with pytest.raises(ValidationFailed):
        ctx.orders.update(o.order_id, OrderPatch(items=[OrderItemIn(sku="SES-18L", qty=3)]))
    ctx.orders.update(o.order_id, OrderPatch(note="기사님 연락함"))  # 특이사항은 허용

    o = ctx.orders.unship(o.order_id)
    assert o.status == "출고대기" and o.shipped_at is None
    o = ctx.orders.cancel(o.order_id)
    assert o.status == "취소"
    with pytest.raises(ValidationFailed):
        ctx.orders.ship(o.order_id)

    names = [e[0] for e in events]
    assert names.count("order.shipped") == 1
    assert "order.unshipped" in names and names[-1] == "order.cancelled"


def test_subscriber_failure_does_not_block_shipping(ctx):
    def broken(_):
        raise RuntimeError("알림톡 서버 오류")

    ctx.bus.subscribe("order.shipped", broken)
    o = _create(ctx, [("SES-18L", 1)], customer_id="C0001")
    assert ctx.orders.ship(o.order_id).status == "출고완료"
    logs = ctx.logs.rows()
    assert any(l["action"] == "출고 후속처리 오류" for l in logs)


# ---------------------------------------------------------------- 조회 / 집계
def test_list_and_production_summary(ctx):
    _create(ctx, [("SES-18L", 10)], customer_id="C0001", due_date=date(2026, 11, 20))
    _create(ctx, [("SES-18L", 5), ("CHI-10KG", 6)], customer_id="C0001", due_date=date(2026, 11, 25))
    done = _create(ctx, [("PER-18L", 3)], customer_id="C0001")
    ctx.orders.ship(done.order_id)

    open_orders = ctx.orders.query(statuses=["접수", "출고대기"])
    assert len(open_orders) == 2
    assert open_orders[0].due_date == date(2026, 11, 20)  # 납기 빠른 순

    s = ctx.orders.production_summary()
    by = {l.sku: l.qty for l in s.lines}
    assert by == {"SES-18L": 15, "CHI-10KG": 6}
    assert (s.parcel_count, s.truck_count) == (1, 1)

    s = ctx.orders.production_summary(until=date(2026, 11, 21))
    assert {l.sku: l.qty for l in s.lines} == {"SES-18L": 10}



def test_order_total_column_and_price_refill(ctx, backend):
    """주문장 '주문합계' 칸 + 주문 뒤에 넣은 가격이 주문을 고칠 때 채워짐"""
    o = _create(ctx, [("SES-18L", 10), ("CHI-5KG", 2)], customer_id="C0001", due_date=date(2026, 11, 20))
    rows = ctx.orders.orders.lines_of(o.order_id, fresh=True)
    assert all(r.get("order_total") == o.total_amount for r in rows)
    # 가격 지우고 → 수정 저장하면 다시 채움
    for r in rows:
        ctx.orders.orders.update_many([((o.order_id, r["line_no"]), {"unit_price": None, "amount": None})])
    from app.schemas.order import OrderPatch

    o2 = ctx.orders.update(o.order_id, OrderPatch(note="가격 채우기"))
    assert o2.total_amount == o.total_amount
