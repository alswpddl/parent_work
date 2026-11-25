"""웹 주문서 서비스.

주문 흐름
  고객: 품목·수량 고르기 → 성함·연락처·주소·받는 날 → 개인정보 동의 → [주문하기]
  서버: 입력 검사 → 거래처 찾기/등록 → 주문장에 저장 (단가는 개인판매가, 택배비 계산)
        → 부모님 카톡 알림 / 고객 주문 접수 알림톡 (켜져 있으면)
  조회: 주문번호 + 전화번호 뒤 4자리

거래처 연결 규칙 (남의 번호로 주문해 그 거래처 월말 정산에 끼워 넣는 것을 막는다)
  - 같은 휴대폰 번호 + 이름(성함 또는 상호)이 거래처명·담당자·별칭과 맞으면 → 그 거래처
  - 번호는 같은데 이름이 다르면 → 새 개인 고객으로 등록하고 메모에 '확인 필요' 남김
  - 번호가 처음이면 → 새 고객 (상호를 적었으면 B2B, 아니면 B2C)

장난 주문 막기
  - 휴대폰 번호 형식 검사, 숨김 칸(봇만 채우는 칸)이 채워지면 거절
  - 같은 번호 1시간 3건, 같은 접속 주소(IP) 1시간 10건까지
  - 조회는 IP 당 10분 30회
  - 같은 주문서에서 [주문하기]가 두 번 눌려도 (client_token 이 같으면) 주문은 1건만 생긴다
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
from ...schemas.settings import WEEKDAYS_KO, AppSettings, closed_weekdays
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


def _norm(s: str) -> str:
    return re.sub(r"[\s()（）·.,-]", "", s or "").lower()


def first_open_day(start: date, closed: set[int]) -> date:
    d = start
    for _ in range(7):
        if d.weekday() not in closed:
            return d
        d += timedelta(days=1)
    return start  # 7일 다 쉬는 날로 적어 둔 경우엔 막지 않는다


# ---------------------------------------------------------------- 입출력 모델
class ShopProduct(BaseModel):
    sku: str
    name: str
    spec: str
    unit: str
    unit_kg: float
    price: int | None  # 가격 숨김 설정이면 None
    description: str
    sold_out: bool = False


class ShopInfo(BaseModel):
    factory_name: str
    factory_phone: str
    notice: str
    show_prices: bool
    bank_account: str
    min_due_date: date
    closed_weekdays: list[int]  # 0=월 … 6=일. 받는 날로 못 고르는 요일
    closed_days_text: str  # "일" / "토, 일"
    shipping_fee: int  # 0 이면 '확인 후 안내'
    free_shipping_over: int  # 0 이면 무료 기준 없음
    threshold_kg: float  # 이 무게 이상이면 화물 (택배비 대신 운임 별도)
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
    client_token: str = Field(default="", max_length=64, description="같은 주문서의 중복 제출 막기")

    @field_validator("name", "company", "address", "zipcode", "note", "client_token", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip()


class GuestOrderOut(BaseModel):
    order_id: str
    created_at: str
    items: str
    due_date: str
    ship_method: str
    subtotal: int | None  # 상품 금액 (가격을 보이는 설정일 때만)
    shipping_fee: int | None  # 택배비. None 이면 확인 후 안내
    estimated_total: int | None  # 상품 + 택배비 (둘 다 정해졌을 때만)
    shipping_note: str  # 택배비 안내 한 줄
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
    "· 이용 목적: 주문 확인, 상품 배송, 배송·입금 안내 연락\n"
    "· 보관 기간: {retention} (관련 법령에서 더 길게 보관하도록 정한 경우 그 기간)\n"
    "· 동의하지 않으실 수 있으나, 그 경우 주문을 받을 수 없어요.\n"
    "· 문의: {factory} {phone}"
)


def shipping_for(st: AppSettings, subtotal: int | None, method: str) -> tuple[int | None, str]:
    """(택배비, 안내 문구). 택배비를 모르면 None."""
    if method == "화물":
        return None, "양이 많아 화물로 보내요. 운임은 확인 후 안내드려요."
    if st.shop_free_shipping_over and subtotal is not None and subtotal >= st.shop_free_shipping_over:
        return 0, "택배비 무료"
    if st.shop_shipping_fee:
        note = f"택배비 {st.shop_shipping_fee:,}원"
        if st.shop_free_shipping_over:
            note += f" ({st.shop_free_shipping_over:,}원 이상 무료)"
        return st.shop_shipping_fee, note
    return None, "택배비는 확인 후 안내드려요."


class WebOrderService:
    TOKEN_TTL = 3600

    def __init__(self, ctx: Any):
        self.ctx = ctx
        self.phone_limiter = _Limiter(3, 3600, "같은 번호로 주문이 너무 많이 들어왔어요. 전화로 문의해 주세요.")
        self.ip_limiter = _Limiter(10, 3600, "주문이 너무 많이 들어왔어요. 잠시 뒤 다시 해 주세요.")
        self.lookup_limiter = _Limiter(30, 600, "조회가 너무 많아요. 잠시 뒤 다시 해 주세요.")
        self._done: dict[str, tuple[float, GuestOrderOut]] = {}  # client_token → 결과
        self._place_lock = threading.Lock()

    # ---------------------------------------------------------------- 주문서 정보
    def _visible_products(self) -> list:
        return [p for p in self.ctx.products.list() if p.shop_visible]

    def _min_due(self, st: AppSettings) -> date:
        return first_open_day(today() + timedelta(days=st.self_order_lead_days), closed_weekdays(st.closed_days))

    def info(self) -> ShopInfo:
        st = self.ctx.settings.load()
        if not st.shop_enabled:
            raise NotFoundError(f"지금은 웹 주문을 받지 않아요. {st.factory_phone or ''}로 연락 주세요.".strip())
        closed = sorted(closed_weekdays(st.closed_days))
        return ShopInfo(
            factory_name=st.factory_name or "주문서",
            factory_phone=st.factory_phone,
            notice=st.shop_notice,
            show_prices=st.shop_show_prices,
            bank_account=st.bank_account,
            min_due_date=self._min_due(st),
            closed_weekdays=closed,
            closed_days_text=", ".join(WEEKDAYS_KO[i] for i in closed),
            shipping_fee=st.shop_shipping_fee if st.shop_show_prices else 0,
            free_shipping_over=st.shop_free_shipping_over if st.shop_show_prices else 0,
            threshold_kg=st.threshold_kg,
            privacy_text=PRIVACY_TEMPLATE.format(
                retention=st.privacy_retention or "주문일로부터 1년", factory=st.factory_name, phone=st.factory_phone
            ),
            products=[
                ShopProduct(
                    sku=p.sku, name=p.name, spec=p.spec, unit=p.unit, unit_kg=p.unit_kg,
                    price=p.shop_price if st.shop_show_prices else None, description=p.description,
                    sold_out=p.sold_out,
                )
                for p in sorted(self._visible_products(), key=lambda p: (p.sold_out, p.name, p.unit_kg))
            ],
        )

    # ---------------------------------------------------------------- 거래처
    @staticmethod
    def _same_person(c: CustomerOut, body: GuestOrderIn) -> bool:
        mine = {_norm(body.name), _norm(body.company)} - {""}
        theirs = {_norm(c.name), _norm(c.contact_name), *(_norm(a) for a in c.aliases.replace("，", ",").split(","))} - {""}
        return any(m == t or (len(m) >= 2 and len(t) >= 2 and (m in t or t in m)) for m in mine for t in theirs)

    def _find_or_create_customer(self, body: GuestOrderIn, phone: str) -> CustomerOut:
        target = digits(phone)
        same_phone = [
            CustomerOut.from_row(d)
            for d in self.ctx.customers.rows(fresh=True)
            if d.get("customer_id") and digits(d.get("phone", "")) == target and d.get("active") is not False
        ]
        match = next((c for c in same_phone if self._same_person(c, body)), None)
        if match:
            self.ctx.customers.update((match.customer_id,), {"privacy_agreed_at": now()})
            return match

        existing = [d.get("customer_id") or "" for d in self.ctx.customers.rows()]
        cid = next_seq_id(existing, "C")
        name = body.company or body.name
        memo = "웹 주문서로 처음 주문"
        if same_phone:
            memo += f" · 확인 필요: 번호가 {', '.join(c.name for c in same_phone)}({', '.join(c.customer_id for c in same_phone)})와 같아요"
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
            "memo": memo,
            "active": True,
        }
        self.ctx.customers.insert(row)
        self.ctx.logs.write("거래처 자동 등록", cid, f"{name} (웹 주문서)", actor="웹주문서")
        return CustomerOut.from_row(row)

    # ---------------------------------------------------------------- 주문
    def _validate(self, body: GuestOrderIn, st: AppSettings) -> None:
        if not st.shop_enabled:
            raise ValidationFailed("지금은 웹 주문을 받지 않아요.")
        if body.website:  # 봇이 숨김 칸을 채움
            raise ValidationFailed("주문을 받을 수 없어요. 전화로 문의해 주세요.")
        if not body.agree_privacy:
            raise ValidationFailed("개인정보 수집·이용에 동의해 주셔야 주문할 수 있어요.")
        if not MOBILE_RE.match(digits(body.phone)):
            raise ValidationFailed("휴대폰 번호를 확인해 주세요 (예: 010-1234-5678).")
        visible = {p.sku: p for p in self._visible_products()}
        for it in body.items:
            p = visible.get(it.sku)
            if p is None:
                raise ValidationFailed("주문할 수 없는 품목이 들어 있어요. 새로고침 후 다시 골라 주세요.")
            if p.sold_out:
                raise ValidationFailed(f"{p.display_name}은(는) 지금 품절이에요. 빼고 주문해 주세요.")
        if body.due_date:
            min_due = self._min_due(st)
            if body.due_date < min_due:
                raise ValidationFailed(f"받는 날은 {fmt_date_ko(min_due)} 이후로 골라 주세요.")
            if body.due_date > today() + timedelta(days=90):
                raise ValidationFailed("받는 날은 3개월 안으로 골라 주세요.")
            if body.due_date.weekday() in closed_weekdays(st.closed_days):
                raise ValidationFailed(f"{WEEKDAYS_KO[body.due_date.weekday()]}요일은 택배가 쉬어요. 다른 날을 골라 주세요.")

    def _cached(self, token: str) -> GuestOrderOut | None:
        if not token:
            return None
        t = time.monotonic()
        for k in [k for k, (ts, _) in self._done.items() if t - ts > self.TOKEN_TTL]:
            del self._done[k]
        hit = self._done.get(token)
        return hit[1] if hit else None

    def place(self, body: GuestOrderIn, client_ip: str = "") -> GuestOrderOut:
        st = self.ctx.settings.load()
        self._validate(body, st)
        phone_d = digits(body.phone)

        # 같은 주문서가 두 번 들어오면(두 번 누름·느린 인터넷 재시도) 처음 결과를 그대로 돌려준다
        with self._place_lock:
            cached = self._cached(body.client_token)
            if cached:
                return cached
            self.phone_limiter.check(phone_d)
            if client_ip:
                self.ip_limiter.check(client_ip)

            phone = pretty_phone(phone_d)
            customer = self._find_or_create_customer(body, phone)
            # 택배비는 상품 금액·출고방식이 정해져야 알 수 있어 먼저 견적을 낸다
            pmap = self.ctx.products.map()
            subtotal: int | None = 0
            for it in body.items:
                price = pmap[it.sku].shop_price
                subtotal = None if subtotal is None or price is None else subtotal + price * it.qty
            kg = sum(pmap[it.sku].unit_kg * it.qty for it in body.items)
            method_guess = "화물" if st.threshold_kg and kg >= st.threshold_kg else "택배"
            fee, _ = shipping_for(st, subtotal, method_guess)

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
                    shipping_fee=fee or 0,
                ),
                actor=f"웹주문서:{body.name}",
                retail=True,
            )
            self.phone_limiter.hit(phone_d)
            if client_ip:
                self.ip_limiter.hit(client_ip)

            # 실제 출고방식(거래처 기본값 반영)으로 안내를 다시 맞춘다
            fee, note = shipping_for(st, order.total_amount, order.ship_method)
            if order.ship_method == "화물" and order.shipping_fee:
                order = self.ctx.orders.set_fields(order.order_id, {"shipping_fee": None}, publish=None)
            show = st.shop_show_prices
            subtotal_out = order.total_amount if show else None
            out = GuestOrderOut(
                order_id=order.order_id,
                created_at=order.created_at.strftime("%m/%d %H:%M") if order.created_at else "",
                items=", ".join(f"{l.product_name} {l.qty}개" for l in order.lines),
                due_date=fmt_date_ko(order.due_date) if order.due_date else "가장 빠른 날",
                ship_method=order.ship_method,
                subtotal=subtotal_out,
                shipping_fee=fee if show else None,
                estimated_total=subtotal_out + fee if show and subtotal_out is not None and fee is not None else None,
                shipping_note=note if show else "금액은 확인 후 안내드려요.",
                bank_account=st.bank_account,
                factory_phone=st.factory_phone,
            )
            if body.client_token:
                self._done[body.client_token] = (time.monotonic(), out)
            return out

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
