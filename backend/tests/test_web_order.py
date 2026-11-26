from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.errors import NotFoundError, TooManyRequests, ValidationFailed
from app.core.timeutil import today
from app.modules.q2_web_order.service import GuestOrderIn
from app.schemas.order import OrderCreate, OrderItemIn
from app.schemas.settings import SettingsPatch


def _svc(ctx):
    return ctx.services["web_order"]


def _body(**kw) -> GuestOrderIn:
    base = dict(
        name="김영희", phone="010-7777-8888", address="서울시 마포구 월드컵로 1 101호", zipcode="03955",
        items=[OrderItemIn(sku="SES-18L", qty=2)], agree_privacy=True,
    )
    base.update(kw)
    return GuestOrderIn(**base)


def test_shop_info_lists_visible_products_and_privacy(full_ctx):
    full_ctx.products.update(("CHI-10KG",), {"shop_visible": False})
    info = _svc(full_ctx).info()
    assert {p.sku for p in info.products} == {"SES-18L", "PER-18L", "CHI-5KG"}
    assert info.products[0].price is not None and info.show_prices
    assert "개인정보 수집·이용 동의" in info.privacy_text and "주문일로부터 1년" in info.privacy_text
    assert info.min_due_date == today() + timedelta(days=1)

    full_ctx.settings.save(SettingsPatch(shop_show_prices=False))
    assert all(p.price is None for p in _svc(full_ctx).info().products)
    full_ctx.settings.save(SettingsPatch(shop_enabled=False))
    with pytest.raises(NotFoundError):
        _svc(full_ctx).info()


def test_new_guest_becomes_customer_and_order_is_saved(full_ctx, http):
    out = _svc(full_ctx).place(_body(note="문 앞에 두세요"), "1.2.3.4")
    assert out.subtotal == 2 * 38000 and out.shipping_fee is None and out.estimated_total is None
    assert "확인 후" in out.shipping_note and out.bank_account.startswith("농협")
    order = full_ctx.orders.get(out.order_id)
    assert order.source == "웹주문서" and order.recipient == "김영희" and order.phone == "010-7777-8888"
    assert order.ship_method == "택배" and order.note == "문 앞에 두세요"
    c = full_ctx.customers.by_id(order.customer_id)
    assert c.type == "B2C" and c.name == "김영희" and c.address.startswith("서울시")
    raw = full_ctx.customers.get(order.customer_id)
    assert raw["privacy_agreed_at"] is not None
    # 사장님 카톡 알림
    assert any("새 웹 주문" in x["form"]["template_object"] for x in http.by("memo/default/send"))


def test_company_name_and_existing_customer_matching(full_ctx):
    out = _svc(full_ctx).place(_body(name="박실장", company="행복마트 본점", phone="01022223333"), "1.1.1.1")
    order = full_ctx.orders.get(out.order_id)
    assert order.customer_id == "C0002"  # 같은 번호 + 이름이 맞음 → 기존 거래처로 연결
    assert order.ship_method == "화물"  # 행복마트 기본 출고방식
    assert len(full_ctx.customers.list()) == 2  # 새로 만들지 않음

    out = _svc(full_ctx).place(_body(name="최사장", company="새가게", phone="010-5555-1234"), "1.1.1.2")
    c = full_ctx.customers.by_id(full_ctx.orders.get(out.order_id).customer_id)
    assert c.name == "새가게" and c.contact_name == "최사장" and c.type == "B2B"


def test_same_phone_but_different_name_is_not_linked(full_ctx):
    """남의 거래처 번호를 적어도 그 거래처 월말 정산에 끼어들지 못한다."""
    out = _svc(full_ctx).place(_body(name="모르는사람", phone="010-2222-3333"), "1.1.1.3")
    order = full_ctx.orders.get(out.order_id)
    assert order.customer_id not in ("C0001", "C0002")
    c = full_ctx.customers.by_id(order.customer_id)
    assert c.type == "B2C" and "확인 필요" in c.memo and "C0002" in c.memo


def test_retail_price_and_shipping_fee(full_ctx):
    full_ctx.products.update(("SES-18L",), {"retail_price": 42000})
    full_ctx.settings.save(SettingsPatch(shop_shipping_fee=4000, shop_free_shipping_over=100000))
    info = _svc(full_ctx).info()
    assert next(p for p in info.products if p.sku == "SES-18L").price == 42000
    assert info.shipping_fee == 4000 and info.free_shipping_over == 100000

    out = _svc(full_ctx).place(_body(), "1.1.1.4")  # 42,000 × 2 = 84,000 → 택배비 4,000
    assert (out.subtotal, out.shipping_fee, out.estimated_total) == (84000, 4000, 88000)
    order = full_ctx.orders.get(out.order_id)
    assert order.lines[0].unit_price == 42000 and order.shipping_fee == 4000  # 주문장에도 개인판매가로

    out = _svc(full_ctx).place(_body(phone="010-1212-3434", items=[OrderItemIn(sku="SES-18L", qty=3)]), "1.1.1.4")
    assert (out.shipping_fee, out.estimated_total, out.shipping_note) == (0, 126000, "택배비 무료")


def test_truck_orders_get_no_parcel_fee(full_ctx):
    full_ctx.settings.save(SettingsPatch(shop_shipping_fee=4000))
    out = _svc(full_ctx).place(_body(items=[OrderItemIn(sku="SES-18L", qty=40)]), "1.1.1.5")  # 40 × 1.7kg ≥ 50kg
    assert out.ship_method == "화물" and out.shipping_fee is None and "운임" in out.shipping_note
    assert full_ctx.orders.get(out.order_id).shipping_fee == 0


def test_sold_out_and_closed_days(full_ctx):
    full_ctx.products.update(("PER-18L",), {"sold_out": True})
    info = _svc(full_ctx).info()
    assert info.products[-1].sku == "PER-18L" and info.products[-1].sold_out  # 품절은 맨 아래
    with pytest.raises(ValidationFailed, match="품절"):
        _svc(full_ctx).place(_body(items=[OrderItemIn(sku="PER-18L", qty=1)]))

    assert info.closed_weekdays == [6] and info.min_due_date.weekday() != 6
    d = today() + timedelta(days=2)
    sunday = d + timedelta(days=(6 - d.weekday()) % 7)
    with pytest.raises(ValidationFailed, match="일요일"):
        _svc(full_ctx).place(_body(due_date=sunday))
    full_ctx.settings.save(SettingsPatch(closed_days="없음"))
    assert _svc(full_ctx).place(_body(due_date=sunday), "1.1.1.6").order_id


def test_double_submit_creates_one_order(full_ctx):
    s = _svc(full_ctx)
    a = s.place(_body(client_token="tok-1"), "1.1.1.7")
    b = s.place(_body(client_token="tok-1"), "1.1.1.7")
    assert a.order_id == b.order_id
    assert len([o for o in full_ctx.orders.query() if o.source == "웹주문서"]) == 1


def test_paid_flag_and_settlement_skips_individuals(full_ctx):
    from app.modules.q4_settlement.service import GenerateIn

    guest = _svc(full_ctx).place(_body(), "1.1.1.8")  # 개인 고객
    b2b = full_ctx.orders.create(OrderCreate(customer_id="C0001", items=[OrderItemIn(sku="SES-18L", qty=1)]))
    prepaid = full_ctx.orders.create(OrderCreate(customer_id="C0001", items=[OrderItemIn(sku="SES-18L", qty=5)]))
    o = full_ctx.orders.set_paid(prepaid.order_id, True)
    assert o.paid_at is not None
    assert _svc(full_ctx).lookup(guest.order_id, "8888", "9.9.9.1").paid is False
    for oid in (guest.order_id, b2b.order_id, prepaid.order_id):
        full_ctx.orders.ship(oid)
    period = f"{today():%Y-%m}"
    r = full_ctx.services["settlement"].generate(GenerateIn(period=period))
    assert [(x.customer_id, x.order_count) for x in r.settlements] == [("C0001", 1)]
    assert full_ctx.orders.set_paid(prepaid.order_id, False).paid_at is None


def test_settings_accept_won_text(full_ctx):
    full_ctx.settings.update(("shop_shipping_fee",), {"value": "3,500원"})
    assert full_ctx.settings.load().shop_shipping_fee == 3500


def test_validation_rules(full_ctx):
    s = _svc(full_ctx)
    with pytest.raises(ValidationFailed, match="개인정보"):
        s.place(_body(agree_privacy=False))
    with pytest.raises(ValidationFailed, match="휴대폰"):
        s.place(_body(phone="02-123-4567"))
    with pytest.raises(ValidationFailed):
        s.place(_body(website="http://spam"))  # 숨김 칸
    with pytest.raises(ValidationFailed, match="받는 날"):
        s.place(_body(due_date=today()))
    full_ctx.products.update(("PER-18L",), {"shop_visible": False})
    with pytest.raises(ValidationFailed, match="주문할 수 없는 품목"):
        s.place(_body(items=[OrderItemIn(sku="PER-18L", qty=1)]))


def test_rate_limits(full_ctx):
    s = _svc(full_ctx)
    for _ in range(3):
        s.place(_body(), "9.9.9.9")
    with pytest.raises(TooManyRequests):
        s.place(_body(), "9.9.9.9")  # 같은 번호 1시간 3건
    for i in range(7):
        s.place(_body(phone=f"010-1111-{i:04d}"), "9.9.9.9")
    with pytest.raises(TooManyRequests):
        s.place(_body(phone="010-1111-9999"), "9.9.9.9")  # 같은 IP 1시간 10건


def test_lookup_needs_matching_phone_tail(full_ctx):
    out = _svc(full_ctx).place(_body(), "2.2.2.2")
    r = _svc(full_ctx).lookup(out.order_id.lower(), "8888", "3.3.3.3")
    assert r.order_id == out.order_id and r.status == "접수"
    with pytest.raises(NotFoundError):
        _svc(full_ctx).lookup(out.order_id, "1234", "3.3.3.3")
    with pytest.raises(NotFoundError):
        _svc(full_ctx).lookup("O-20000101-001", "8888", "3.3.3.3")
    with pytest.raises(ValidationFailed):
        _svc(full_ctx).lookup(out.order_id, "88", "3.3.3.3")


def test_lead_days_per_product(full_ctx):
    """품목마다 준비일이 다르면 가장 오래 걸리는 품목 기준"""
    from datetime import timedelta

    from app.modules.q2_self_order.service import lead_for

    st = full_ctx.settings.load()
    full_ctx.products.update(("PER-18L",), {"lead_days": 3})
    p = full_ctx.products.map()["PER-18L"]
    assert p.lead_days == 3
    assert lead_for(st, [p]) == 3
    assert lead_for(st, []) == st.self_order_lead_days
    s = _svc(full_ctx)
    info = s.info()
    assert any(x.sku == "PER-18L" and x.lead_days == 3 for x in info.products)
    with pytest.raises(ValidationFailed, match="받는 날"):
        s.place(_body(items=[OrderItemIn(sku="PER-18L", qty=1)], due_date=today() + timedelta(days=1)))


def test_quiet_hours():
    from datetime import time

    from app.schemas.settings import in_quiet_hours

    assert in_quiet_hours("20:00-07:00", time(23, 30))
    assert in_quiet_hours("20:00-07:00", time(6, 59))
    assert not in_quiet_hours("20:00-07:00", time(7, 0))
    assert not in_quiet_hours("", time(2, 0))
    assert not in_quiet_hours("엉터리", time(2, 0))
