"""웹 주문서 서비스.

주문 흐름
  고객: 품목·수량 고르기 → 성함·연락처·주소·받는 날 → 개인정보 동의 → [주문하기]
  서버: 입력 검사 → 같은 휴대폰 번호의 거래처가 있으면 연결, 없으면 개인(B2C) 거래처로 새로 등록
        → 주문장에 저장 (무게 계산·택배/화물 자동 분류는 기존 주문 서비스가 그대로 처리)
        → 부모님 카톡 알림 / 고객 주문 접수 알림톡 (켜져 있으면)
  조회: 주문번호 + 전화번호 뒤 4자리

장난 주문 막기
  - 휴대폰 번호 형식 검사, 숨김 칸(봇만 채우는 칸)이 채워지면 거절
  - 같은 번호 1시간 3건, 같은 접속 주소(IP) 1시간 10건까지
  - 조회는 IP 당 10분 30회
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field, field_validator

from ...core.errors import NotFoundError, TooManyRequests, ValidationFailed
from ...core.ids import next_seq_id
from ...core.timeutil import fmt_date_ko, now, today
from ...schemas.customer import CustomerOut
from ...schemas.order import OrderCreate, OrderItemIn, OrderOut
from ..q2_self_order.service import PublicOrderOut, to_public

MOBILE_RE = re.compile(r"^01[016789]\d{7,8}$")


def digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def pretty_phone(s: str) -> str:
    d = digits(s)
    if len(d) == 11:
        return f"{d[:3]}-{d[3:7]}-{d[7:]}"
    if len(d) == 10:
        return f"{d[:3]}-{d[3:6]}-{d[6:]}"
    return s.strip()


# ---------------------------------------------------------------- 입출력 모델
class ShopProduct(BaseModel):
    sku: str
    name: str
    spec: str
    unit: str
    unit_kg: float
    price: int | None  # 가격 숨김 설정이면 None
    description: str


class ShopInfo(BaseModel):
    factory_name: str
    factory_phone: str
    notice: str
    show_prices: bool
    bank_account: str
    min_due_date: date
    privacy_text: str
    products: list[ShopProduct]


class GuestOrderIn(BaseModel):
    name: str = Field(min_length=1, max_length=30, description="받는 분 성함")
    company: str = Field(default="", max_length=40, description="상호 (가게·식당 이름, 선택)")
    phone: str = Field(min_length=9, max_length=20)
    address: str = Field(min_length=5, max_length=200)
    zipcode: str = Field(default="", max_length=10)
    due_date: date | None = None
    note: str = Field(default="", max_length=300)
    items: list[OrderItemIn] = Field(min_length=1, max_length=30)
    agree_privacy: bool
    website: str = Field(default="", max_length=200, description="숨김 칸 — 사람은 비워 둔다")

    @field_validator("name", "company", "address", "zipcode", "note", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip()


class GuestOrderOut(BaseModel):
    order_id: str
    created_at: str
    items: str
    due_date: str
    ship_method: str
    estimated_total: int | None  # 가격을 보이는 설정일 때만
    bank_account: str
    factory_phone: str


class _Limiter:
    def __init__(self, n: int, window: int, message: str):
        self.n, self.window, self.message = n, window, message
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str) -> None:
        t = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and t - q[0] > self.window:
                q.popleft()
            if len(q) >= self.n:
                raise TooManyRequests(self.message)

    def hit(self, key: str) -> None:
        with self.lock:
            self.hits[key].append(time.monotonic())


PRIVACY_TEMPLATE = (
    "[개인정보 수집·이용 동의]\n"
    "· 수집 항목: 성함, 상호(선택), 휴대폰 번호, 배송 주소\n"
    "· 이용 목적: 주문 확인, 상품 배송, 배송·정산 안내 연락\n"
    "· 보관 기간: {retention} (관련 법령에서 더 길게 보관하도록 정한 경우 그 기간)\n"
    "· 동의하지 않으실 수 있으나, 그 경우 주문을 받을 수 없어요.\n"
    "· 문의: {factory} {phone}"
)


class WebOrderService:
    def __init__(self, ctx: Any):
        self.ctx = ctx
        self.phone_limiter = _Limiter(3, 3600, "같은 번호로 주문이 너무 많이 들어왔어요. 전화로 문의해 주세요.")
        self.ip_limiter = _Limiter(10, 3600, "주문이 너무 많이 들어왔어요. 잠시 뒤 다시 해 주세요.")
        self.lookup_limiter = _Limiter(30, 600, "조회가 너무 많아요. 잠시 뒤 다시 해 주세요.")

    # ---------------------------------------------------------------- 주문서 정보
    def _visible_products(self) -> list:
        return [p for p in self.ctx.products.list() if p.shop_visible]

    def info(self) -> ShopInfo:
        st = self.ctx.settings.load()
        if not st.shop_enabled:
            raise NotFoundError(f"지금은 웹 주문을 받지 않아요. {st.factory_phone or ''}로 연락 주세요.".strip())
        return ShopInfo(
            factory_name=st.factory_name or "주문서",
            factory_phone=st.factory_phone,
            notice=st.shop_notice,
            show_prices=st.shop_show_prices,
            bank_account=st.bank_account,
            min_due_date=today() + timedelta(days=st.self_order_lead_days),
            privacy_text=PRIVACY_TEMPLATE.format(
                retention=st.privacy_retention or "주문일로부터 1년", factory=st.factory_name, phone=st.factory_phone
            ),
            products=[
                ShopProduct(
                    sku=p.sku, name=p.name, spec=p.spec, unit=p.unit, unit_kg=p.unit_kg,
                    price=p.unit_price if st.shop_show_prices else None, description=p.description,
                )
                for p in self._visible_products()
            ],
        )

    # ---------------------------------------------------------------- 주문
    def _find_or_create_customer(self, body: GuestOrderIn, phone: str) -> CustomerOut:
        """같은 휴대폰 번호의 거래처가 있으면 그 거래처로, 없으면 개인 고객으로 새로 등록."""
        target = digits(phone)
        for d in self.ctx.customers.rows(fresh=True):
            if d.get("customer_id") and digits(d.get("phone", "")) == target and d.get("active") is not False:
                self.ctx.customers.update((d["customer_id"],), {"privacy_agreed_at": now()})
                return CustomerOut.from_row(d)
        existing = [d.get("customer_id") or "" for d in self.ctx.customers.rows()]
        cid = next_seq_id(existing, "C")
        name = body.company or body.name
        row = {
            "customer_id": cid,
            "name": name,
            "aliases": body.name if body.company else "",
            "type": "B2B" if body.company else "B2C",
            "contact_name": body.name,
            "phone": phone,
            "address": body.address,
            "zipcode": body.zipcode,
            "default_method": "자동",
            "notify_opt_in": True,
            "privacy_agreed_at": now(),
            "memo": "웹 주문서로 처음 주문",
            "active": True,
        }
        self.ctx.customers.insert(row)
        self.ctx.logs.write("거래처 자동 등록", cid, f"{name} (웹 주문서)", actor="웹주문서")
        return CustomerOut.from_row(row)

    def place(self, body: GuestOrderIn, client_ip: str = "") -> GuestOrderOut:
        st = self.ctx.settings.load()
        if not st.shop_enabled:
            raise ValidationFailed("지금은 웹 주문을 받지 않아요.")
        if body.website:  # 봇이 숨김 칸을 채움
            raise ValidationFailed("주문을 받을 수 없어요. 전화로 문의해 주세요.")
        if not body.agree_privacy:
            raise ValidationFailed("개인정보 수집·이용에 동의해 주셔야 주문할 수 있어요.")
        phone_d = digits(body.phone)
        if not MOBILE_RE.match(phone_d):
            raise ValidationFailed("휴대폰 번호를 확인해 주세요 (예: 010-1234-5678).")
        visible = {p.sku: p for p in self._visible_products()}
        for it in body.items:
            if it.sku not in visible:
                raise ValidationFailed("주문할 수 없는 품목이 들어 있어요. 새로고침 후 다시 골라 주세요.")
        min_due = today() + timedelta(days=st.self_order_lead_days)
        if body.due_date and body.due_date < min_due:
            raise ValidationFailed(f"받는 날은 {fmt_date_ko(min_due)} 이후로 골라 주세요.")
        if body.due_date and body.due_date > today() + timedelta(days=90):
            raise ValidationFailed("받는 날은 3개월 안으로 골라 주세요.")

        self.phone_limiter.check(phone_d)
        if client_ip:
            self.ip_limiter.check(client_ip)

        phone = pretty_phone(phone_d)
        customer = self._find_or_create_customer(body, phone)
        order: OrderOut = self.ctx.orders.create(
            OrderCreate(
                customer_id=customer.customer_id,
                customer_name=customer.name,
                recipient=body.name,
                phone=phone,
                address=body.address,
                zipcode=body.zipcode,
                due_date=body.due_date,
                note=body.note,
                items=body.items,
                source="웹주문서",
            ),
            actor=f"웹주문서:{body.name}",
        )
        self.phone_limiter.hit(phone_d)
        if client_ip:
            self.ip_limiter.hit(client_ip)

        total = None
        if st.shop_show_prices:
            amounts = [l.amount for l in order.lines]
            total = sum(a for a in amounts if a is not None) if all(a is not None for a in amounts) else None
        return GuestOrderOut(
            order_id=order.order_id,
            created_at=order.created_at.strftime("%m/%d %H:%M") if order.created_at else "",
            items=", ".join(f"{l.product_name} {l.qty}개" for l in order.lines),
            due_date=fmt_date_ko(order.due_date),
            ship_method=order.ship_method,
            estimated_total=total,
            bank_account=st.bank_account,
            factory_phone=st.factory_phone,
        )

    # ---------------------------------------------------------------- 조회
    def lookup(self, order_id: str, phone_tail: str, client_ip: str = "") -> PublicOrderOut:
        key = client_ip or "anon"
        self.lookup_limiter.check(key)
        self.lookup_limiter.hit(key)
        tail = digits(phone_tail)
        oid = (order_id or "").strip().upper()
        if len(tail) != 4 or not oid:
            raise ValidationFailed("주문번호와 전화번호 뒤 4자리를 넣어 주세요.")
        try:
            o = self.ctx.orders.get(oid)
        except NotFoundError:
            o = None
        if o is None or not digits(o.phone).endswith(tail):
            raise NotFoundError("주문을 찾지 못했어요. 주문번호와 전화번호를 확인해 주세요.")
        return to_public(o)
