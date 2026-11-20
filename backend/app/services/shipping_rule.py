"""택배 / 화물 분기 규칙 — 1분기 핵심 로직.

우선순위
1. 화면에서 직접 고른 값(수동)
2. 거래처 기본출고방식이 '택배'/'화물'로 지정돼 있으면 그 값(거래처기본)
3. 주문 총중량 >= 화물 기준 무게 → 화물, 아니면 택배(자동)
"""

from __future__ import annotations

import math
from typing import Iterable

from ..schemas.product import ProductOut
from ..schemas.settings import AppSettings


def decide_method(
    order_kg: float,
    settings: AppSettings,
    *,
    manual: str | None = None,
    customer_default: str | None = None,
) -> tuple[str, str]:
    if manual in ("택배", "화물"):
        return manual, "수동"
    if customer_default in ("택배", "화물"):
        return customer_default, "거래처기본"
    return ("화물" if order_kg >= settings.threshold_kg else "택배"), "자동"


def pallet_count(order_kg: float, settings: AppSettings) -> int:
    if order_kg <= 0:
        return 0
    return max(1, math.ceil(order_kg / settings.pallet_kg))


def box_count(lines: Iterable[tuple[int, ProductOut | None]]) -> int:
    """(수량, 품목) 목록 → 예상 택배 박스 수. 박스입수가 없으면 그 품목은 1박스로 본다."""
    total = 0
    for qty, product in lines:
        if qty <= 0:
            continue
        upb = product.units_per_box if product else None
        total += math.ceil(qty / upb) if upb else 1
    return total


def line_kg(qty: int, product: ProductOut | None) -> float:
    if not product:
        return 0.0
    return round(qty * product.unit_kg, 3)
