from __future__ import annotations

from app.core.timeutil import today
from app.demo_data import seed_history
from app.modules.q4_settlement.service import GenerateIn, prev_period


def test_full_demo_data_drives_every_screen(full_ctx):
    seed_history(full_ctx)
    board = full_ctx.orders.query(statuses=["접수", "출고대기"])
    assert {o.ship_method for o in board} == {"택배", "화물"}
    assert [s.customer_id for s in full_ctx.services["reorder"].reminders()] == ["C0001"]
    r = full_ctx.services["settlement"].generate(GenerateIn(period=prev_period(today())))
    assert len(r.settlements) >= 2
    text = full_ctx.services["briefing"].preview().text
    assert "주문할 때 된 거래처" in text and "자재 재고" in text
