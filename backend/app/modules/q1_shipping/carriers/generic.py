from __future__ import annotations

from .base import CarrierFormat, boxes, item_summary, message, recipient

FORMAT = CarrierFormat(
    code="generic",
    name="공통 양식",
    verified=True,  # 우리 쪽에서 정한 양식이므로 확인 완료로 둔다
    sheet_name="택배발송",
    text_columns=("받는분 전화", "받는분 우편번호", "보내는분 전화"),
    columns=(
        ("주문번호", lambda o, s: o.order_id, 18),
        ("받는분", recipient, 12),
        ("받는분 전화", lambda o, s: o.phone, 15),
        ("받는분 우편번호", lambda o, s: o.zipcode, 10),
        ("받는분 주소", lambda o, s: o.address, 45),
        ("품목명", lambda o, s: item_summary(o), 40),
        ("박스수량", boxes, 8),
        ("중량(kg)", lambda o, s: o.order_kg, 9),
        ("배송메시지", message, 28),
        ("보내는분", lambda o, s: s.factory_name, 12),
        ("보내는분 전화", lambda o, s: s.factory_phone, 15),
        ("보내는분 주소", lambda o, s: s.factory_address, 40),
    ),
)
