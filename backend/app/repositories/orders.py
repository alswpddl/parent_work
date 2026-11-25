"""주문장 탭. 1행 = 품목 1줄. 주문번호로 묶어 OrderOut 으로 돌려준다."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from ..core.repository import Repository
from ..core.sheet_schema import ORDERS
from ..schemas.order import OrderLineOut, OrderOut

# 주문 단위로 모든 라인에 같은 값이 들어가는 열 (헤더 필드)
HEADER_FIELDS = (
    "created_at", "source", "customer_id", "customer_name", "order_kg", "ship_method", "method_by",
    "recipient", "phone", "address", "zipcode", "due_date", "note", "status", "shipped_at",
    "carrier", "tracking_no", "truck_no", "driver_phone", "notified_at", "ext_order_no",
    "stock_deducted", "settlement_id", "updated_at", "shipping_fee", "paid_at",
)


class OrderRepo(Repository[OrderOut]):
    spec = ORDERS

    def grouped(self, fresh: bool = False) -> "OrderedDict[str, list[dict[str, Any]]]":
        groups: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
        for d in self.rows(fresh):
            oid = d.get("order_id")
            if not oid:
                continue
            groups.setdefault(oid, []).append(d)
        for lines in groups.values():
            lines.sort(key=lambda x: x.get("line_no") or 0)
        return groups

    def lines_of(self, order_id: str, fresh: bool = False) -> list[dict[str, Any]]:
        return [d for d in self.rows(fresh) if d.get("order_id") == order_id]

    def all_ids(self, fresh: bool = True) -> list[str]:
        return list(self.grouped(fresh).keys())


def to_order_out(lines: list[dict[str, Any]], *, pallets: int = 0, boxes: int = 0) -> OrderOut:
    """같은 주문번호의 라인들 → OrderOut. 헤더 값은 첫 라인 기준(비어 있으면 다음 라인에서 채움)."""
    lines = sorted(lines, key=lambda x: x.get("line_no") or 0)
    head: dict[str, Any] = {}
    for f in HEADER_FIELDS:
        for ln in lines:
            v = ln.get(f)
            if v not in (None, ""):
                head[f] = v
                break
    raw_text = next((ln.get("raw_text") for ln in lines if ln.get("raw_text")), "")

    out_lines = [
        OrderLineOut(
            line_no=ln.get("line_no") or i + 1,
            sku=ln.get("sku") or "",
            product_name=ln.get("product_name") or "",
            qty=ln.get("qty") or 0,
            line_kg=ln.get("line_kg") or 0,
            unit_price=ln.get("unit_price"),
            amount=ln.get("amount"),
        )
        for i, ln in enumerate(lines)
    ]
    order_kg = head.get("order_kg")
    if order_kg is None:
        order_kg = round(sum(l.line_kg for l in out_lines), 3)
    amounts = [l.amount for l in out_lines if l.amount is not None]

    status = head.get("status") if head.get("status") in ("접수", "출고대기", "출고완료", "취소") else "접수"
    method = head.get("ship_method") if head.get("ship_method") in ("택배", "화물") else "택배"

    return OrderOut(
        order_id=lines[0]["order_id"],
        created_at=head.get("created_at"),
        updated_at=head.get("updated_at"),
        source=head.get("source", ""),
        customer_id=head.get("customer_id", ""),
        customer_name=head.get("customer_name", ""),
        recipient=head.get("recipient", ""),
        phone=head.get("phone", ""),
        address=head.get("address", ""),
        zipcode=head.get("zipcode", ""),
        due_date=head.get("due_date"),
        note=head.get("note", ""),
        status=status,  # type: ignore[arg-type]
        ship_method=method,  # type: ignore[arg-type]
        method_by=head.get("method_by", "자동"),
        order_kg=order_kg,
        pallets=pallets,
        boxes=boxes,
        # 단가가 빠진 줄이 하나라도 있으면 합계를 보여 주지 않는다 (일부만 더한 금액은 오해를 부른다)
        total_amount=sum(amounts) if amounts and len(amounts) == len(out_lines) else None,
        shipping_fee=head.get("shipping_fee") or 0,
        paid_at=head.get("paid_at"),
        shipped_at=head.get("shipped_at"),
        carrier=head.get("carrier", ""),
        tracking_no=head.get("tracking_no", ""),
        truck_no=head.get("truck_no", ""),
        driver_phone=head.get("driver_phone", ""),
        notified_at=head.get("notified_at"),
        ext_order_no=head.get("ext_order_no", ""),
        stock_deducted=bool(head.get("stock_deducted")),
        settlement_id=head.get("settlement_id", ""),
        raw_text=raw_text or "",
        lines=out_lines,
    )
