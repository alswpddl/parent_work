from __future__ import annotations

import pytest

from app.core.errors import TooManyRequests, UnauthorizedError, ValidationFailed
from app.modules.q2_web_order.accounts import check_password, hash_password
from app.modules.q2_web_order.service import GuestOrderIn, LoginIn, PasswordIn, ProfilePatch, SignupIn
from app.schemas.order import OrderItemIn


def _svc(ctx):
    return ctx.services["web_order"]


def _signup(ctx, **kw):
    base = dict(name="김영희", phone="010-7777-8888", password="1234", address="서울시 마포구 1", agree_privacy=True)
    base.update(kw)
    return _svc(ctx).signup(SignupIn(**base))


def _order(**kw):
    base = dict(name="김영희", phone="010-7777-8888", address="서울시 마포구 1", items=[OrderItemIn(sku="SES-18L", qty=1)], agree_privacy=True)
    base.update(kw)
    return GuestOrderIn(**base)


def test_password_hash_roundtrip():
    h = hash_password("1234")
    assert h.startswith("pbkdf2$") and "1234" not in h
    assert check_password("1234", h) and not check_password("1235", h) and not check_password("1234", "garbage")


def test_signup_login_me_and_orders(full_ctx):
    a = _signup(full_ctx)
    assert a.profile.name == "김영희" and a.profile.address == "서울시 마포구 1"
    with pytest.raises(ValidationFailed, match="이미 가입"):
        _signup(full_ctx)
    b = _svc(full_ctx).login(LoginIn(phone="01077778888", password="1234"), "1.1.1.1")
    assert _svc(full_ctx).me(b.token).phone == "010-7777-8888"

    # 로그인 주문: 받는 분이 달라도(선물) 내 주문 내역에 쌓인다
    out = _svc(full_ctx).place(_order(name="엄마", phone="010-5555-6666", address="부산시 1"), "1.1.1.1", b.token)
    assert out.token == b.token
    mine = _svc(full_ctx).my_orders(b.token)
    assert [m.order_id for m in mine] == [out.order_id] and mine[0].recipient == "엄마"
    assert mine[0].lines[0].qty == 1 and mine[0].paid is False


def test_wrong_password_and_rate_limit(full_ctx):
    _signup(full_ctx)
    for _ in range(10):
        with pytest.raises(ValidationFailed, match="맞지 않아요"):
            _svc(full_ctx).login(LoginIn(phone="010-7777-8888", password="0000"), "2.2.2.2")
    with pytest.raises(TooManyRequests):
        _svc(full_ctx).login(LoginIn(phone="010-7777-8888", password="1234"), "2.2.2.2")


def test_password_change_invalidates_old_token_and_reset(full_ctx):
    a = _signup(full_ctx)
    with pytest.raises(ValidationFailed, match="지금 비밀번호"):
        _svc(full_ctx).change_password(a.token, PasswordIn(old_password="9999", new_password="5678"))
    b = _svc(full_ctx).change_password(a.token, PasswordIn(old_password="1234", new_password="5678"))
    with pytest.raises(UnauthorizedError):
        _svc(full_ctx).me(a.token)
    assert _svc(full_ctx).me(b.token).name == "김영희"
    # 부모님이 비밀번호 초기화 → 토큰 막힘, 다시 가입 가능
    cid = next(c.customer_id for c in full_ctx.customers.list() if c.phone == "010-7777-8888")
    full_ctx.customers.update((cid,), {"web_password": ""})
    with pytest.raises(UnauthorizedError):
        _svc(full_ctx).me(b.token)
    assert _signup(full_ctx, password="4321").token
    with pytest.raises(UnauthorizedError):
        _svc(full_ctx).me("forged.token")


def test_cannot_take_over_parent_registered_customer(full_ctx):
    """부모님이 등록한 거래처(행복마트)의 번호·담당자 이름을 알아도 그 거래처 주문 내역은 못 본다."""
    a = _signup(full_ctx, name="박실장", company="행복마트", phone="010-2222-3333")
    c = full_ctx.customers.by_id(next(x.customer_id for x in full_ctx.customers.list() if "확인 필요" in x.memo))
    assert c.customer_id != "C0002" and "C0002" in c.memo
    assert _svc(full_ctx).my_orders(a.token) == []


def test_order_with_password_creates_account(full_ctx):
    out = _svc(full_ctx).place(_order(password="2468"), "3.3.3.3")
    assert out.token
    assert _svc(full_ctx).my_orders(out.token)[0].order_id == out.order_id
    # 이미 가입한 번호로 비회원 주문 + 비밀번호 → 기존 비밀번호는 그대로
    again = _svc(full_ctx).place(_order(password="9999"), "3.3.3.3")
    assert again.token == ""
    assert _svc(full_ctx).login(LoginIn(phone="010-7777-8888", password="2468"), "3.3.3.3").token


def test_update_profile(full_ctx):
    a = _signup(full_ctx, company="새가게", name="최사장")
    p = _svc(full_ctx).update_me(a.token, ProfilePatch(address="부산시 새주소 9", zipcode="48-000", company="새가게 본점"))
    assert p.address == "부산시 새주소 9" and p.zipcode == "48000" and p.company == "새가게 본점" and p.name == "최사장"
