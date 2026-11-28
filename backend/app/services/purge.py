"""시험으로 넣은 주문을 장부에서 완전히 지우기 (관리자 전용).

순서: 아직 안 취소된 주문은 먼저 '취소' → 재고가 원래대로 돌아오고, 카드 결제면 환불까지
      → 주문장 줄 삭제 → 그 주문의 후기 삭제 → _기록에 남김
월말 정산에 들어간 주문은 명세서와 어긋나서 지우지 않는다.
"""

from __future__ import annotations

from typing import Any


def purge_orders(ctx: Any, order_ids: list[str], actor: str = "관리자") -> dict:
    deleted: list[str] = []
    skipped: list[dict[str, str]] = []
    reviews = None
    web = ctx.services.get("web_order")
    if web is not None:
        try:
            reviews = web._reviews  # 후기 탭
        except Exception:  # noqa: BLE001 — 후기 탭이 없어도 주문 삭제는 진행
            reviews = None
    for oid in dict.fromkeys(o.strip() for o in order_ids if o and o.strip()):
        lines = ctx.orders_repo.lines_of(oid, fresh=True)
        if not lines:
            skipped.append({"order_id": oid, "reason": "없는 주문이에요"})
            continue
        if any(ln.get("settlement_id") for ln in lines):
            skipped.append({"order_id": oid, "reason": "월말 정산에 들어간 주문이라 지울 수 없어요"})
            continue
        try:
            ctx.orders.cancel(oid, actor=actor)  # 재고 되돌리기·카드 환불
        except Exception as e:  # noqa: BLE001
            skipped.append({"order_id": oid, "reason": f"취소하지 못했어요: {e}"})
            continue
        lines = ctx.orders_repo.lines_of(oid, fresh=True)
        ctx.orders_repo.delete_many([(oid, ln.get("line_no")) for ln in lines])
        if reviews is not None:
            gone = [(d["review_id"],) for d in reviews.rows(fresh=True) if d.get("order_id") == oid and d.get("review_id")]
            if gone:
                reviews.delete_many(gone)
        ctx.logs.write("주문 완전 삭제", oid, lines[0].get("customer_name", "") if lines else "", actor=actor)
        deleted.append(oid)
    return {"deleted": deleted, "skipped": skipped}
