"""테스트 주문 완전 삭제"""
from app.services.purge import purge_orders
from tests.test_web_order import _body, _svc


def test_purge_cancels_then_deletes_lines_and_reviews(full_ctx):
    s = _svc(full_ctx)
    a = s.place(_body(client_token="p1"))
    b = s.place(_body(client_token="p2"))
    keep = s.place(_body(client_token="p3"))
    # b 는 출고까지 → 후기 하나
    full_ctx.orders.ship(b.order_id)
    full_ctx.orders.complete(b.order_id) if hasattr(full_ctx.orders, "complete") else None
    s._reviews.insert({"review_id": "R99999", "order_id": b.order_id, "product_name": "x", "rating": 5, "text": "시험", "hidden": False})
    # 정산에 들어간 주문은 못 지움
    full_ctx.orders_repo.update_many([((keep.order_id, 1), {"settlement_id": "S1"})])

    r = purge_orders(full_ctx, [a.order_id, b.order_id, keep.order_id, "NOPE"])
    assert set(r["deleted"]) == {a.order_id, b.order_id}
    reasons = {x["order_id"]: x["reason"] for x in r["skipped"]}
    assert "정산" in reasons[keep.order_id] and "없는" in reasons["NOPE"]
    ids = full_ctx.orders_repo.all_ids()
    assert a.order_id not in ids and b.order_id not in ids and keep.order_id in ids
    assert not [d for d in s._reviews.rows(fresh=True) if d.get("order_id") == b.order_id]
    assert any(l.get("action") == "주문 완전 삭제" for l in full_ctx.logs.rows(fresh=True))
