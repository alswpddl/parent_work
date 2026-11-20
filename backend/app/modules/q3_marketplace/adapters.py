"""오픈마켓 주문 엑셀 → 공통 형식.

판매자센터에서 내려받은 '발주(주문) 엑셀'의 열 이름 후보를 적어 둔다.
마켓이 열 이름을 바꾸면 여기 후보에 새 이름을 추가하면 된다 (첫 번째로 값이 있는 열을 쓴다).

⚠️ 스마트스토어 엑셀은 보통 비밀번호가 걸려 내려온다 → 엑셀에서 열어 비밀번호 해제 후 .xlsx 로 다시 저장해서 올린다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Adapter:
    code: str
    source: str  # 주문장 '경로' 값
    fields: dict[str, list[str]]


SMARTSTORE = Adapter(
    code="smartstore",
    source="스마트스토어",
    fields={
        "order_no": ["주문번호"],
        "line_no": ["상품주문번호"],
        "recipient": ["수취인명", "수취인"],
        "phone": ["수취인연락처1", "수취인 연락처1", "수취인연락처", "수취인 연락처"],
        "address": ["통합배송지", "배송지", "기본배송지", "수취인주소"],
        "address2": ["상세배송지"],
        "zipcode": ["우편번호", "수취인우편번호"],
        "product": ["상품명"],
        "option": ["옵션정보", "옵션"],
        "qty": ["수량", "주문수량"],
        "message": ["배송메세지", "배송메시지"],
    },
)

COUPANG = Adapter(
    code="coupang",
    source="쿠팡",
    fields={
        "order_no": ["주문번호"],
        "line_no": ["묶음배송번호", "옵션ID"],
        "recipient": ["수취인이름", "수취인명", "수취인"],
        "phone": ["수취인전화번호", "수취인 전화번호", "수취인연락처"],
        "address": ["수취인 주소", "수취인주소", "배송지"],
        "address2": [],
        "zipcode": ["우편번호", "수취인우편번호"],
        "product": ["등록상품명", "노출상품명(옵션명)", "노출상품명", "상품명"],
        "option": ["등록옵션명", "옵션명"],
        "qty": ["구매수(수량)", "구매수", "수량"],
        "message": ["배송메세지", "배송메시지"],
    },
)

ADAPTERS: dict[str, Adapter] = {a.code: a for a in (SMARTSTORE, COUPANG)}


def detection_hints(adapter: Adapter) -> dict[str, list[str]]:
    keys = ("order_no", "recipient", "phone", "address", "product", "qty")
    return {k: adapter.fields[k] for k in keys}
