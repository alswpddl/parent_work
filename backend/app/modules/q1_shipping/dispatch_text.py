"""화물 배차 요청 문자 — 화물 콜센터·단골 기사님께 카톡으로 그대로 붙여넣는 글."""

from __future__ import annotations

from ...core.timeutil import fmt_date_ko
from ...schemas.order import OrderOut
from ...schemas.settings import AppSettings
from ...services.shipping_rule import pallet_count


def _kg(v: float) -> str:
    return f"{v:,.1f}".rstrip("0").rstrip(".")


def build_dispatch_text(o: OrderOut, s: AppSettings) -> str:
    load_place = s.factory_address or "(기본 정보에 공장 주소를 넣어 주세요)"
    if s.factory_name:
        load_place += f" / {s.factory_name}"
    items = ", ".join(f"{l.product_name} {l.qty}개" for l in o.lines)
    lines = [
        "[화물 배차 요청]",
        f"상차지: {load_place}",
        f"상차 연락처: {s.factory_phone or '-'}",
        f"하차지: {o.address or '-'}",
        f"받는 곳: {o.customer_name}" + (f" ({o.recipient})" if o.recipient and o.recipient != o.customer_name else ""),
        f"받는 곳 연락처: {o.phone or '-'}",
        f"품목: {items}",
        f"총 중량: 약 {_kg(o.order_kg)}kg / 파레트 {pallet_count(o.order_kg, s)}개",
        f"도착 희망: {fmt_date_ko(o.due_date)}",
    ]
    if o.note:
        lines.append(f"특이사항: {o.note}")
    lines.append(f"(주문번호 {o.order_id})")
    return "\n".join(lines)
