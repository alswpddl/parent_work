"""Google Sheets 통합 DB 스키마 — 단일 정의(Single Source of Truth).

- 1행은 부모님이 읽는 한국어 헤더, 코드는 영문 key 로 다룬다.
- 2~4분기 열도 여기서 미리 정의해 1분기부터 시트에 만들어 둔다(빈칸).
  → 이후 분기 기능을 붙여도 시트 구조를 바꿀 일이 없다.
- 열 순서는 시트에서 부모님이 바꿔도 된다. 코드는 헤더 텍스트로 열을 찾는다.
- 부모님이 직접 추가한 열(메모, 수식 등)은 건드리지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ColType = Literal["str", "int", "float", "bool", "date", "datetime"]


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    type: ColType = "str"
    text: bool = False  # 시트 서식을 '일반 텍스트'로 고정 (전화번호·송장번호 앞자리 0, 지수표기 방지)
    quarter: int = 1


@dataclass(frozen=True)
class TabSpec:
    name: str  # 코드에서 부르는 이름
    title: str  # 시트 탭 제목
    columns: tuple[Column, ...]
    key_fields: tuple[str, ...]  # 행을 찾는 기본키 (복합키 가능)

    @property
    def headers(self) -> list[str]:
        return [c.header for c in self.columns]

    @property
    def text_headers(self) -> list[str]:
        return [c.header for c in self.columns if c.text]

    def column(self, key: str) -> Column:
        for c in self.columns:
            if c.key == key:
                return c
        raise KeyError(key)

    @property
    def keys(self) -> list[str]:
        return [c.key for c in self.columns]


C = Column

# ---------------------------------------------------------------------------
# Orders (주문장) — 1행 = 품목 1줄. 같은 주문은 주문번호를 공유한다.
# ---------------------------------------------------------------------------
ORDERS = TabSpec(
    name="orders",
    title="주문장",
    key_fields=("order_id", "line_no"),
    columns=(
        C("order_id", "주문번호"),
        C("line_no", "라인", "int"),
        C("created_at", "접수일시", "datetime"),
        C("source", "경로"),
        C("customer_id", "거래처ID"),
        C("customer_name", "거래처명"),
        C("sku", "품목코드"),
        C("product_name", "품목명"),
        C("qty", "수량", "int"),
        C("line_kg", "라인중량", "float"),
        C("order_kg", "주문총중량", "float"),
        C("ship_method", "출고방식"),
        C("method_by", "방식결정"),
        C("recipient", "받는분"),
        C("phone", "연락처", text=True),
        C("address", "배송지"),
        C("zipcode", "우편번호", text=True),
        C("due_date", "납기일", "date"),
        C("note", "특이사항"),
        C("status", "상태"),
        C("unit_price", "단가", "int"),
        C("amount", "공급가액", "int"),
        C("shipping_fee", "배송비", "int", quarter=2),
        C("shipped_at", "출고일시", "datetime"),
        C("paid_at", "입금확인", "datetime", quarter=2),
        C("carrier", "택배사", quarter=3),
        C("tracking_no", "송장번호", text=True, quarter=3),
        C("truck_no", "차량번호", quarter=3),
        C("driver_phone", "기사연락처", text=True, quarter=3),
        C("notified_at", "알림발송", "datetime", quarter=3),
        C("ext_order_no", "외부주문번호", text=True, quarter=3),
        C("stock_deducted", "재고차감", "bool", quarter=4),
        C("settlement_id", "정산ID", quarter=4),
        C("raw_text", "원문"),
        C("updated_at", "수정일시", "datetime"),
    ),
)

# ---------------------------------------------------------------------------
# Customers (거래처마스터)
# ---------------------------------------------------------------------------
CUSTOMERS = TabSpec(
    name="customers",
    title="거래처",
    key_fields=("customer_id",),
    columns=(
        C("customer_id", "거래처ID"),
        C("name", "거래처명"),
        C("aliases", "별칭"),
        C("type", "구분"),
        C("contact_name", "담당자"),
        C("phone", "연락처", text=True),
        C("address", "배송지"),
        C("zipcode", "우편번호", text=True),
        C("default_method", "기본출고방식"),
        C("order_token", "주문링크토큰", quarter=2),
        C("privacy_agreed_at", "개인정보동의", "datetime", quarter=2),
        C("web_password", "웹로그인(암호화)", quarter=2),  # 손님이 정한 비밀번호의 해시. 지우면 비밀번호 초기화
        C("notify_opt_in", "알림톡수신", "bool", quarter=3),
        C("biz_no", "사업자번호", text=True, quarter=4),
        C("owner_name", "대표자", quarter=4),
        C("email", "이메일", quarter=4),
        C("last_order_date", "최근주문일", "date", quarter=4),
        C("avg_interval_days", "평균주문간격", "float", quarter=4),
        C("reorder_snooze_until", "리마인드보류", "date", quarter=4),
        C("memo", "메모"),
        C("active", "사용", "bool"),
    ),
)

# ---------------------------------------------------------------------------
# Products (품목규격)
# ---------------------------------------------------------------------------
PRODUCTS = TabSpec(
    name="products",
    title="품목",
    key_fields=("sku",),
    columns=(
        C("sku", "품목코드"),
        C("name", "품목명"),
        C("spec", "규격"),
        C("aliases", "별칭"),
        C("unit", "단위"),
        C("unit_kg", "개당중량", "float"),
        C("units_per_box", "박스입수", "int"),
        C("unit_price", "공급단가", "int"),
        C("retail_price", "개인판매가", "int", quarter=2),
        C("description", "설명", quarter=2),
        C("shop_visible", "주문서노출", "bool", quarter=2),
        C("sold_out", "품절", "bool", quarter=2),
        C("lead_days", "준비일", "int", quarter=2),  # 주문 후 며칠 뒤부터 받을 수 있나 (비우면 _설정 기본값)
        C("image_url", "사진주소", quarter=2),
        C("tax_type", "과세구분", quarter=4),
        C("container_item", "용기자재", quarter=4),
        C("box_item", "박스자재", quarter=4),
        C("label_item", "라벨자재", quarter=4),
        C("lid_item", "뚜껑자재", quarter=4),
        C("bulk_item", "저장고품목", quarter=4),  # 출고하면 내용량(kg)×수량만큼 저장고에서 빠짐
        C("net_kg", "내용량kg", "float", quarter=4),  # 비우면 규격(1kg, 500g)에서 읽음
        C("active", "사용", "bool"),
    ),
)

# ---------------------------------------------------------------------------
# Inventory (원부자재재고) — 4분기
# ---------------------------------------------------------------------------
INVENTORY = TabSpec(
    name="inventory",
    title="자재재고",
    key_fields=("item_id",),
    columns=(
        C("item_id", "자재코드", quarter=4),
        C("category", "분류", quarter=4),
        C("name", "자재명", quarter=4),
        C("unit", "단위", quarter=4),
        C("stock", "현재고", "float", quarter=4),  # 저장고 젓갈은 kg 소수점
        C("safety_stock", "안전재고", "float", quarter=4),
        C("reorder_qty", "권장발주량", "float", quarter=4),
        C("supplier", "매입처", quarter=4),
        C("supplier_phone", "매입처연락처", text=True, quarter=4),
        C("last_alert_at", "마지막경고", "datetime", quarter=4),
        C("updated_at", "수정일시", "datetime", quarter=4),
    ),
)

# ---------------------------------------------------------------------------
# Settlements (월말정산) — 4분기
# ---------------------------------------------------------------------------
SETTLEMENTS = TabSpec(
    name="settlements",
    title="월말정산",
    key_fields=("settlement_id",),
    columns=(
        C("settlement_id", "정산ID", quarter=4),
        C("period", "정산월", text=True, quarter=4),
        C("customer_id", "거래처ID", quarter=4),
        C("customer_name", "거래처명", quarter=4),
        C("order_count", "납품건수", "int", quarter=4),
        C("supply_amount", "공급가액", "int", quarter=4),
        C("vat", "세액", "int", quarter=4),
        C("total", "합계", "int", quarter=4),
        C("pdf_url", "PDF링크", quarter=4),
        C("status", "상태", quarter=4),
        C("sent_at", "발송일시", "datetime", quarter=4),
        C("paid_at", "수금일", "date", quarter=4),
        C("memo", "메모", quarter=4),
    ),
)

# ---------------------------------------------------------------------------
# 보조 탭
# ---------------------------------------------------------------------------
SETTINGS = TabSpec(
    name="settings",
    title="_설정",
    key_fields=("key",),
    columns=(
        C("key", "키"),
        C("label", "항목"),
        C("value", "값", text=True),
        C("description", "설명"),
    ),
)

LOGS = TabSpec(
    name="logs",
    title="_기록",
    key_fields=("ts", "action", "target"),
    columns=(
        C("ts", "일시", "datetime"),
        C("actor", "작업자"),
        C("action", "동작"),
        C("target", "대상"),
        C("detail", "내용"),
        C("result", "결과"),
    ),
)

# 오픈마켓 상품명 → 우리 품목코드 매핑 (3분기). 한 번 고르면 다음부터 자동.
MARKET_MAP = TabSpec(
    name="market_map",
    title="_상품매핑",
    key_fields=("source", "external_name"),
    columns=(
        C("source", "경로", quarter=3),
        C("external_name", "외부상품명", quarter=3),
        C("sku", "품목코드", quarter=3),
        C("multiplier", "수량배수", "int", quarter=3),
        C("updated_at", "수정일시", "datetime", quarter=3),
    ),
)

# 자재 입출고 이력 (4분기) — 부모님이 '왜 재고가 줄었지?' 를 확인하는 곳
STOCK_MOVES = TabSpec(
    name="stock_moves",
    title="_재고이력",
    key_fields=("ts", "item_id"),
    columns=(
        C("ts", "일시", "datetime", quarter=4),
        C("item_id", "자재코드", quarter=4),
        C("item_name", "자재명", quarter=4),
        C("change", "변동", "float", quarter=4),
        C("stock_after", "변동후재고", "float", quarter=4),
        C("reason", "사유", quarter=4),
        C("order_id", "주문번호", quarter=4),
    ),
)

ALL_TABS: tuple[TabSpec, ...] = (
    ORDERS, CUSTOMERS, PRODUCTS, INVENTORY, SETTLEMENTS, SETTINGS, LOGS, MARKET_MAP, STOCK_MOVES,
)

# ---------------------------------------------------------------------------
# 시스템 시트 (부모님과 공유하지 않는 비공개 스프레드시트 권장)
#   SYSTEM_SPREADSHEET_ID 가 없으면 본 시트에 '_토큰', '_발송기록' 으로 만든다.
# ---------------------------------------------------------------------------
SYS_TOKENS = TabSpec(
    name="sys_tokens",
    title="토큰",
    key_fields=("key",),
    columns=(
        C("key", "키"),
        C("value", "값", text=True),
        C("expires_at", "만료일시", "datetime"),
        C("updated_at", "수정일시", "datetime"),
    ),
)

SYS_MESSAGES = TabSpec(
    name="sys_messages",
    title="발송기록",
    key_fields=("ts", "to"),
    columns=(
        C("ts", "일시", "datetime"),
        C("channel", "채널"),  # 카카오(나에게) / 알림톡 / 이메일
        C("kind", "종류"),  # 브리핑 / 재고경고 / 택배출고 / 화물출고 / 명세서 ...
        C("to", "수신", text=True),
        C("order_id", "주문번호"),
        C("result", "결과"),  # 성공 / 실패 / 건너뜀
        C("content", "내용"),
        C("error", "오류"),
    ),
)

SYSTEM_TABS: tuple[TabSpec, ...] = (SYS_TOKENS, SYS_MESSAGES)
