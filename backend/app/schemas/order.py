from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from .common import MethodBy, OrderSource, OrderStatus, ShipMethod


# ---------------------------------------------------------------------------
# 카톡 파싱 → 초안
# ---------------------------------------------------------------------------
class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    use_ai: bool = True


class Candidate(BaseModel):
    id: str
    label: str
    score: float


class DraftCustomer(BaseModel):
    customer_id: str | None = None
    name: str = ""  # 메시지에서 읽은 이름 또는 매칭된 거래처명
    matched: bool = False
    candidates: list[Candidate] = []


class DraftItem(BaseModel):
    sku: str | None = None
    raw_name: str = ""  # 메시지에 적힌 그대로
    product_name: str = ""  # 매칭된 품목 표시명
    qty: int = 0
    unit_kg: float = 0
    line_kg: float = 0
    matched: bool = False
    candidates: list[Candidate] = []


class OrderDraft(BaseModel):
    parser: str  # "ai" | "rule"
    customer: DraftCustomer
    recipient: str = ""
    phone: str = ""
    address: str = ""
    zipcode: str = ""
    due_date: date | None = None
    note: str = ""
    items: list[DraftItem] = []
    order_kg: float = 0
    ship_method: ShipMethod = "택배"
    method_by: MethodBy = "자동"
    pallets: int = 0
    threshold_kg: float = 50
    warnings: list[str] = []
    raw_text: str = ""


# ---------------------------------------------------------------------------
# 저장 / 수정
# ---------------------------------------------------------------------------
class OrderItemIn(BaseModel):
    sku: str = Field(min_length=1)
    qty: int = Field(ge=1, le=100000)


class OrderCreate(BaseModel):
    customer_id: str | None = None
    customer_name: str = Field(default="", max_length=60)
    recipient: str = ""
    phone: str = ""
    address: str = ""
    zipcode: str = ""
    due_date: date | None = None
    note: str = Field(default="", max_length=500)
    items: list[OrderItemIn] = Field(min_length=1, max_length=50)
    ship_method: ShipMethod | None = Field(default=None, description="비우면 자동 분류")
    source: OrderSource = "카톡"
    raw_text: str = Field(default="", max_length=5000)
    ext_order_no: str = Field(default="", max_length=60, description="오픈마켓 주문번호 (중복 방지)")
    shipping_fee: int = Field(default=0, ge=0, le=1_000_000)

    @field_validator("customer_name", "recipient", "phone", "address", "zipcode", "note", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip()


class OrderPatch(BaseModel):
    """출고완료·취소는 전용 엔드포인트로만 바꾼다(이벤트 발행 때문)."""

    customer_id: str | None = None
    customer_name: str | None = None
    recipient: str | None = None
    phone: str | None = None
    address: str | None = None
    zipcode: str | None = None
    due_date: date | None = None
    note: str | None = None
    ship_method: ShipMethod | None = None
    auto_method: bool = Field(default=False, description="true 면 수동 지정을 풀고 무게 기준으로 다시 분류")
    status: OrderStatus | None = Field(default=None, description="접수/출고대기 사이만 변경 가능")
    items: list[OrderItemIn] | None = Field(default=None, min_length=1, max_length=50)


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------
class OrderLineOut(BaseModel):
    line_no: int
    sku: str
    product_name: str
    qty: int
    line_kg: float
    unit_price: int | None = None
    amount: int | None = None


class OrderOut(BaseModel):
    order_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    source: str = ""
    customer_id: str = ""
    customer_name: str = ""
    recipient: str = ""
    phone: str = ""
    address: str = ""
    zipcode: str = ""
    due_date: date | None = None
    note: str = ""
    status: OrderStatus = "접수"
    ship_method: ShipMethod = "택배"
    method_by: str = "자동"
    order_kg: float = 0
    pallets: int = 0
    boxes: int = 0
    total_amount: int | None = None
    shipping_fee: int = 0
    shipped_at: datetime | None = None
    paid_at: datetime | None = None  # 입금 확인 시각 (웹 주문)
    # 3분기
    carrier: str = ""
    tracking_no: str = ""
    truck_no: str = ""
    driver_phone: str = ""
    notified_at: datetime | None = None
    ext_order_no: str = ""
    stock_deducted: bool = False
    settlement_id: str = ""
    raw_text: str = ""
    lines: list[OrderLineOut] = []


class OrderListOut(BaseModel):
    orders: list[OrderOut]
    count: int


class ProductionLine(BaseModel):
    sku: str
    product_name: str
    qty: int
    kg: float
    order_count: int


class ProductionSummary(BaseModel):
    until: date | None
    lines: list[ProductionLine]
    parcel_count: int
    truck_count: int
    order_count: int
