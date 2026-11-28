"""주문 단계 '도착': 손님 잘 받았어요 · 관리자 · 출고 며칠 뒤 자동"""
from datetime import timedelta

import pytest

from app.core.errors import ValidationFailed
from app.core.timeutil import now
from app.modules.q2_web_order.extras import CancelIn
from tests.test_web_order import _body, _svc


def test_received_and_auto(full_ctx):
    s = _svc(full_ctx)
    a = s.place(_body(client_token="d1"))
    with pytest.raises(ValidationFailed, match="보낸"):
        s.received_by_customer(CancelIn(order_id=a.order_id, phone4="8888"))
    full_ctx.orders.ship(a.order_id)
    out = s.received_by_customer(CancelIn(order_id=a.order_id, phone4="8888"))
    assert out.delivered and out.status == "출고완료"
    assert full_ctx.orders.get(a.order_id).delivered_at is not None
    # 출고 되돌리면 도착도 지워짐
    full_ctx.orders.unship(a.order_id)
    assert full_ctx.orders.get(a.order_id, fresh=True).delivered_at is None

    # 자동: 출고 4일 지난 주문만
    b = s.place(_body(client_token="d2"))
    c = s.place(_body(client_token="d3"))
    full_ctx.orders.ship(b.order_id)
    full_ctx.orders.ship(c.order_id)
    full_ctx.orders_repo.update_many([((b.order_id, 1), {"shipped_at": now() - timedelta(days=4)})])
    r = full_ctx.jobs.run("auto_delivered", full_ctx)
    assert r["delivered"] == [b.order_id]
    assert full_ctx.orders.get(c.order_id, fresh=True).delivered_at is None
    # 관리자 되돌리기
    assert full_ctx.orders.mark_delivered(b.order_id, False).delivered_at is None
