from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.signing import verify
from app.core.timeutil import now, today
from app.modules.q4_inventory.service import AdjustIn, ItemIn, ReceiveIn
from app.modules.q4_reorder.service import SnoozeIn
from app.modules.q4_settlement.service import GenerateIn, SendIn, SettlementPatch, prev_period
from app.schemas.order import OrderCreate, OrderItemIn

from .conftest import FakeSMTP


def _order(ctx, cid="C0001", items=(("SES-18L", 7),), **kw):
    return ctx.orders.create(OrderCreate(customer_id=cid, items=[OrderItemIn(sku=s, qty=q) for s, q in items], **kw))


def _stock(ctx, item_id):
    return next(i.stock for i in ctx.services["inventory"].list_items() if i.item_id == item_id)


# ---------------------------------------------------------------- 재고
def test_ship_deducts_materials_and_unship_restores(full_ctx):
    inv = full_ctx.services["inventory"]
    before = {i.item_id: i.stock for i in inv.list_items()}
    o = _order(full_ctx, items=(("SES-18L", 7), ("CHI-5KG", 3)))
    full_ctx.orders.ship(o.order_id)
    after = {i.item_id: i.stock for i in inv.list_items()}
    assert before["CT-18L"] - after["CT-18L"] == 7
    assert before["LBL-SES"] - after["LBL-SES"] == 7
    assert before["BOX-6"] - after["BOX-6"] == 2  # 7통 ÷ 6입 → 2박스
    assert before["BAG-5KG"] - after["BAG-5KG"] == 3 and before["BOX-2"] - after["BOX-2"] == 2
    assert full_ctx.orders.get(o.order_id, fresh=True).stock_deducted

    full_ctx.orders.ship(o.order_id)  # 두 번 눌러도 한 번만
    assert _stock(full_ctx, "CT-18L") == after["CT-18L"]

    full_ctx.orders.unship(o.order_id)
    assert _stock(full_ctx, "CT-18L") == before["CT-18L"]
    full_ctx.orders.ship(o.order_id)
    full_ctx.orders.cancel(o.order_id)
    assert _stock(full_ctx, "CT-18L") == before["CT-18L"]
    reasons = [m.reason for m in inv.recent_moves("CT-18L")]
    assert reasons.count("출고 차감") == 2 and "출고취소 복원" in reasons and "주문취소 복원" in reasons


def test_low_stock_alert_once_per_day(full_ctx, http):
    inv = full_ctx.services["inventory"]
    r = inv.check_and_alert()
    assert r["low"] >= 2 and r["alerted"] >= 2
    text = http.by("memo/default/send")[0]["form"]["template_object"]
    assert "10kg 포장봉투" in text and "들기름 라벨" in text
    assert inv.check_and_alert()["alerted"] == 0  # 오늘은 이미 보냄
    assert inv.check_and_alert(force=True)["alerted"] >= 2


def test_receive_adjust_create_and_forecast(full_ctx):
    inv = full_ctx.services["inventory"]
    item = inv.create(ItemIn(name="참기름 뚜껑", category="용기", stock=100, safety_stock=20))
    assert item.item_id == "M0001" and item.status == "정상"
    assert inv.receive("M0001", ReceiveIn(qty=50, memo="OO용기")).stock == 150
    assert inv.adjust("M0001", AdjustIn(stock=140, reason="파손 10개")).stock == 140
    assert [m.change for m in inv.recent_moves("M0001")] == [-10, 50, 100]

    # 출고가 쌓이면 하루 평균 사용량·소진 예상일이 나온다
    o = _order(full_ctx, items=(("SES-18L", 60),))
    full_ctx.orders.ship(o.order_id)
    ct = next(i for i in inv.list_items() if i.item_id == "CT-18L")
    assert ct.avg_daily_use == 2.0 and ct.days_left == pytest.approx((420 - 60) / 2.0)
    assert ct.used_by == ["들기름 1.8L", "참기름 1.8L"] or set(ct.used_by) == {"참기름 1.8L", "들기름 1.8L"}


def test_unknown_material_code_is_flagged(full_ctx):
    full_ctx.products.update(("SES-18L",), {"label_item": "LBL-NONE"})
    o = _order(full_ctx, items=(("SES-18L", 1),))
    full_ctx.orders.ship(o.order_id)
    assert any(l["action"] == "자재코드 없음" for l in full_ctx.logs.rows())


# ---------------------------------------------------------------- 정산
def _ship_last_month(ctx, cid, items, day_offset=5):
    o = _order(ctx, cid=cid, items=items)
    ctx.orders.ship(o.order_id)
    last_month_day = today().replace(day=1) - timedelta(days=day_offset)
    ctx.orders_repo.update_many([((o.order_id, l.line_no), {"shipped_at": now().replace(year=last_month_day.year, month=last_month_day.month, day=last_month_day.day)}) for l in o.lines])
    return o


def test_settlement_generate_vat_and_links(full_ctx):
    period = prev_period(today())
    a = _ship_last_month(full_ctx, "C0001", (("SES-18L", 10), ("CHI-5KG", 2)))  # 과세 380,000 + 면세 190,000
    _ship_last_month(full_ctx, "C0001", (("PER-18L", 1),), day_offset=10)  # 과세 42,000
    _ship_last_month(full_ctx, "C0002", (("CHI-10KG", 10),))  # 면세 1,850,000
    _order(full_ctx, cid="C0001")  # 이번 달·미출고 → 제외

    svc = full_ctx.services["settlement"]
    r = svc.generate(GenerateIn(period=period))
    assert r.created == 2 and not r.warnings
    s1 = next(s for s in r.settlements if s.customer_id == "C0001")
    assert s1.order_count == 2 and s1.supply_amount == 380000 + 190000 + 42000
    assert s1.vat == 38000 + 4200 and s1.total == s1.supply_amount + s1.vat
    assert s1.settlement_id == f"S-{period.replace('-', '')}-C0001"
    assert full_ctx.orders.get(a.order_id, fresh=True).settlement_id == s1.settlement_id
    s2 = next(s for s in r.settlements if s.customer_id == "C0002")
    assert s2.vat == 0

    filename, pdf = svc.pdf(s1.settlement_id)
    assert pdf.startswith(b"%PDF") and len(pdf) > 2000 and "한솥식당" in filename

    link = svc.public_link(s1.settlement_id)
    assert link.startswith("https://api.example.com/api/public/statements/")
    assert verify(full_ctx.config.auth_secret, link.rsplit("/", 1)[1]) == f"stmt:{s1.settlement_id}"


def test_settlement_send_and_regenerate_rules(full_ctx, http):
    period = prev_period(today())
    _ship_last_month(full_ctx, "C0001", (("SES-18L", 3),))
    svc = full_ctx.services["settlement"]
    sid = svc.generate(GenerateIn(period=period)).settlements[0].settlement_id

    out = svc.send(sid, SendIn(via=["email", "kakao"]))
    assert out.results == {"email": "성공", "kakao": "성공"} and out.status == "발송완료"
    mail = FakeSMTP.sent[-1]
    assert mail["To"] == "hansot@example.com" and any(p.get_filename().endswith(".pdf") for p in mail.iter_attachments())
    alim = http.by("api.solapi.com")[-1]["json"]["messages"][0]["kakaoOptions"]
    assert alim["templateId"] == "TPL_S" and alim["variables"]["#{합계}"] == f"{3 * 38000 + 11400:,}"

    # 발송된 건은 다시 만들어도 유지
    r = svc.generate(GenerateIn(period=period))
    assert r.kept == [sid] and r.created == r.updated == 0
    assert svc.generate(GenerateIn(period=period, force=True)).updated == 1

    paid = svc.update(sid, SettlementPatch(status="수금완료"))
    assert paid.status == "수금완료" and paid.paid_at == today()


def test_settlement_missing_price_and_no_email(full_ctx):
    full_ctx.products.update(("PER-18L",), {"unit_price": None})
    _ship_last_month(full_ctx, "C0002", (("PER-18L", 2),))
    svc = full_ctx.services["settlement"]
    r = svc.generate(GenerateIn(period=prev_period(today())))
    assert r.warnings and "들기름" in r.warnings[0]
    out = svc.send(r.settlements[0].settlement_id, SendIn(via=["email"]))
    assert out.results["email"] == "거래처 이메일이 없어요" and out.status == "생성"


def test_unpaid_briefing_section(full_ctx):
    _ship_last_month(full_ctx, "C0001", (("SES-18L", 1),))
    full_ctx.services["settlement"].generate(GenerateIn(period=prev_period(today())))
    sec = full_ctx.services["settlement"].briefing_section(full_ctx, today())
    assert sec and "1건" in sec.lines[0] and "한솥식당" in sec.lines[0]


# ---------------------------------------------------------------- 리마인드
def _backdate(ctx, order, days_ago):
    t = now() - timedelta(days=days_ago)
    ctx.orders_repo.update_many([((order.order_id, l.line_no), {"created_at": t}) for l in order.lines])


def test_reorder_reminders_and_snooze(full_ctx):
    for ago in (40, 33, 26, 19):  # 한솥: 7일마다 → 19일째 소식 없음
        _backdate(full_ctx, _order(full_ctx, cid="C0001"), ago)
    for ago in (30, 16, 2):  # 행복마트: 14일마다 → 아직 여유
        _backdate(full_ctx, _order(full_ctx, cid="C0002", items=(("CHI-10KG", 1),)), ago)

    svc = full_ctx.services["reorder"]
    due = svc.reminders()
    assert [s.customer_id for s in due] == ["C0001"]
    s = due[0]
    assert s.avg_interval_days == 7 and s.days_since == 19 and s.overdue_days == int(19 - 7 * 1.3)

    assert svc.job()["updated"] == 2
    c = full_ctx.customers.by_id("C0001")
    assert c.avg_interval_days == 7 and c.last_order_date == today() - timedelta(days=19)

    sec = svc.briefing_section(full_ctx, today())
    assert sec and "한솥식당" in sec.lines[0]

    svc.snooze("C0001", SnoozeIn(days=5))
    assert svc.reminders() == []
