from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.errors import NotFoundError, TooManyRequests, ValidationFailed
from app.core.timeutil import today
from app.modules.q2_web_order.service import GuestOrderIn
from app.schemas.order import OrderItemIn
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
    assert out.estimated_total == 2 * 38000 and out.bank_account.startswith("농협")
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
    assert order.customer_id == "C0002"  # 같은 휴대폰 번호 → 기존 거래처로 연결
    assert order.ship_method == "화물"  # 행복마트 기본 출고방식
    assert len(full_ctx.customers.list()) == 2  # 새로 만들지 않음

    out = _svc(full_ctx).place(_body(name="최사장", company="새가게", phone="010-5555-1234"), "1.1.1.2")
    c = full_ctx.customers.by_id(full_ctx.orders.get(out.order_id).customer_id)
    assert c.name == "새가게" and c.contact_name == "최사장" and c.type == "B2B"


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
