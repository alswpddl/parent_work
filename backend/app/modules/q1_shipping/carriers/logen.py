"""로젠택배 대량 등록용 — ⚠️ 실제 업로드 양식과 대조 전 초안.

로젠 프로그램(또는 웹)에서 '엑셀 일괄등록' 양식 파일을 받아 1행 열 이름과 순서를
아래 columns 에 그대로 옮겨 적은 뒤 verified=True 로 바꾸면 된다.
"""

from __future__ import annotations

from .base import CarrierFormat, boxes, item_summary, message, recipient

FORMAT = CarrierFormat(
    code="logen",
    name="로젠택배",
    verified=False,
    text_columns=("수하인전화", "수하인우편번호"),
    columns=(
        ("수하인명", recipient, 12),
        ("수하인우편번호", lambda o, s: o.zipcode, 10),
        ("수하인주소", lambda o, s: o.address, 45),
        ("수하인전화", lambda o, s: o.phone, 15),
        ("수량", boxes, 6),
        ("물품명", lambda o, s: item_summary(o), 40),
        ("배송메세지", message, 28),
        ("주문번호", lambda o, s: o.order_id, 18),
    ),
)
