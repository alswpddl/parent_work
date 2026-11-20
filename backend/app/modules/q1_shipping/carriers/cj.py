"""CJ대한통운 대량 등록용 — ⚠️ 실제 업로드 양식과 대조 전 초안.

CJ 택배 예약(기업 고객) 화면에서 받은 엑셀 업로드 양식의 1행 열 이름·순서로 바꾼 뒤
verified=True 로 바꾸면 된다.
"""

from __future__ import annotations

from .base import CarrierFormat, boxes, item_summary, message, recipient

FORMAT = CarrierFormat(
    code="cj",
    name="CJ대한통운",
    verified=False,
    text_columns=("받는분전화번호", "받는분우편번호"),
    columns=(
        ("받는분성명", recipient, 12),
        ("받는분전화번호", lambda o, s: o.phone, 15),
        ("받는분우편번호", lambda o, s: o.zipcode, 10),
        ("받는분주소(전체)", lambda o, s: o.address, 45),
        ("품목명", lambda o, s: item_summary(o), 40),
        ("내품수량", boxes, 8),
        ("배송메세지1", message, 28),
        ("고객주문번호", lambda o, s: o.order_id, 18),
    ),
)
