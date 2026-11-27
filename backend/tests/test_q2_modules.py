from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.errors import NotFoundError, TooManyRequests, ValidationFailed
from app.core.timeutil import today
from app.modules.q2_self_order.service import SelfOrderIn
from app.schemas.order import OrderCreate, OrderItemIn
from app.schemas.settings import SettingsPatch


def _weekday(d):
    """일요일(기본 휴무)이면 월요일로 — 테스트가 요일에 따라 깨지지 않게"""
    return d + timedelta(days=1) if d.weekday() == 6 else d


def _svc(ctx):
    return ctx.services["self_order"]


# ---------------------------------------------------------------- 셀프 주문
def test_link_issue_and_regenerate(full_ctx):
    link = _svc(full_ctx).issue_link("C0001")
    assert link.url == f"https://app.example.com/order/{link.token}" and len(link.token) >= 20
    assert _svc(full_ctx).issue_link("C0001").token == link.token  # 그대로
    new = _svc(full_ctx).issue_link("C0001", regenerate=True)
    assert new.token != link.token
    with pytest.raises(NotFoundError):
        _svc(full_ctx).form(link.token)  # 옛 링크는 막힘
    assert full_ctx.customers.by_id("C0001").has_order_link


def test_form_and_place_order(full_ctx, http):
    tok = _svc(full_ctx).issue_link("C0001").token
    full_ctx.orders.create(OrderCreate(customer_id="C0001", items=[OrderItemIn(sku="SES-18L", qty=6)]))
    form = _svc(full_ctx).form(tok)
    assert form.customer_name == "한솥식당" and len(form.products) == 4
    assert [(f.sku, f.qty) for f in form.last_items] == [("SES-18L", 6)]
    from app.modules.q2_web_order.service import first_open_day

    assert form.min_due_date == first_open_day(today() + timedelta(days=1), {6})  # 일요일 휴무면 월요일

    with pytest.raises(ValidationFailed):
        _svc(full_ctx).place(tok, SelfOrderIn(items=[OrderItemIn(sku="SES-18L", qty=1)], due_date=today()))
    out = _svc(full_ctx).place(
        tok, SelfOrderIn(items=[OrderItemIn(sku="PER-18L", qty=4)], due_date=_weekday(today() + timedelta(days=2)), note="문 앞")
    )
    assert out.status == "접수" and "들기름" in out.items
    saved = full_ctx.orders.get(out.order_id)
    assert saved.source == "셀프주문" and saved.customer_id == "C0001" and saved.address.startswith("서울시")
    # 사장님 카톡 알림
    sent = [c for c in http.by("memo/default/send") if "새 셀프주문" in c["form"]["template_object"]]
    assert sent
    assert [o.order_id for o in _svc(full_ctx).recent(tok)][0] == out.order_id


def test_self_order_notify_can_be_turned_off(full_ctx, http):
    full_ctx.settings.save(SettingsPatch(notify_new_self_order=False))
    tok = _svc(full_ctx).issue_link("C0001").token
    _svc(full_ctx).place(tok, SelfOrderIn(items=[OrderItemIn(sku="PER-18L", qty=1)]))
    assert not http.by("memo/default/send")


def test_bad_token_and_rate_limit(full_ctx):
    with pytest.raises(NotFoundError):
        _svc(full_ctx).form("short")
    with pytest.raises(NotFoundError):
        _svc(full_ctx).form("x" * 24)
    tok = _svc(full_ctx).issue_link("C0002").token
    for _ in range(10):
        _svc(full_ctx).place(tok, SelfOrderIn(items=[OrderItemIn(sku="SES-18L", qty=1)]))
    with pytest.raises(TooManyRequests):
        _svc(full_ctx).place(tok, SelfOrderIn(items=[OrderItemIn(sku="SES-18L", qty=1)]))


def test_inactive_customer_link_blocked(full_ctx):
    tok = _svc(full_ctx).issue_link("C0002").token
    full_ctx.customers.update(("C0002",), {"active": False})
    with pytest.raises(NotFoundError):
        _svc(full_ctx).form(tok)


# ---------------------------------------------------------------- 브리핑
def test_briefing_collects_module_sections(full_ctx):
    full_ctx.orders.create(OrderCreate(customer_id="C0001", items=[OrderItemIn(sku="SES-18L", qty=5)], due_date=today()))
    full_ctx.orders.create(OrderCreate(customer_id="C0002", items=[OrderItemIn(sku="CHI-10KG", qty=6)], due_date=today() - timedelta(days=1)))
    b = full_ctx.services["briefing"].preview()
    titles = [s.title for s in b.sections]
    assert titles[0] == "생산·출고" and "자재 재고" in titles  # 데모 자재 중 10kg 봉투·들기름 라벨이 안전재고 미만
    assert "택배 1건 · 🚚 화물 1건" in b.text and "납기 지난 주문 1건" in b.text
    assert "참기름 1.8L 5개" in b.text
    assert b.kakao_connected


def test_briefing_send_and_disable(full_ctx, http):
    assert full_ctx.jobs.run("morning_briefing", full_ctx)["sent"] is True
    assert http.by("memo/default/send")
    full_ctx.settings.save(SettingsPatch(briefing_enabled=False))
    r = full_ctx.jobs.run("morning_briefing", full_ctx)
    assert r["sent"] is False and "꺼짐" in r["reason"]
    assert full_ctx.services["briefing"].send(force=True)["sent"] is True


def test_all_jobs_registered(full_ctx):
    names = {j.name for j in full_ctx.jobs.list()}
    assert names == {"morning_briefing", "kakao_token_refresh", "stock_check", "monthly_settlement", "reorder_scan"}
    assert full_ctx.jobs.run("kakao_token_refresh", full_ctx)["refreshed"] is True
