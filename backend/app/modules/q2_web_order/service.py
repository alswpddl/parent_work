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

from ...core.errors import NotFoundError, TooManyRequests, UnauthorizedError, ValidationFailed
from ...core.ids import next_seq_id
from ...core.signing import sign, verify
from ...core.timeutil import fmt_date_ko, now, today
from ...schemas.customer import CustomerOut
from ...schemas.order import OrderCreate, OrderItemIn, OrderOut
from ...schemas.settings import WEEKDAYS_KO, AppSettings, closed_weekdays
from ..q2_self_order.service import PublicOrderOut, lead_for, to_public
from .accounts import check_password, hash_password, issue_token, read_token, token_matches

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
    image_url: str = ""
    lead_days: int = 1  # 주문 후 며칠 뒤부터 받을 수 있나


class ShopInfo(BaseModel):
    factory_name: str
    factory_phone: str
    notice: str
    intro: str = ""
    contact_hours: str = ""
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
    pay_client_key: str = ""  # 토스페이먼츠 클라이언트 키 (비면 온라인 결제 없음 — 계좌 입금만)
    pay_test_mode: bool = False  # 테스트 키면 True → 화면에 '테스트 결제' 표시


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
    password: str = Field(default="", max_length=40, description="적으면 다음부터 로그인해서 주문 (가입)")

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
    token: str = ""  # 주문하면서 가입했거나 로그인 상태면 로그인 토큰
    pay_token: str = ""  # 이 주문을 바로 온라인 결제할 때 쓰는 표 (주문 완료 화면 → 결제창)


class PayInfo(BaseModel):
    """결제창 띄우기 전에 서버가 정해 주는 값 — 금액은 브라우저가 아니라 여기서 계산"""
    order_id: str
    order_name: str
    amount: int
    customer_name: str
    client_key: str
    test_mode: bool


class PayConfirmIn(BaseModel):
    payment_key: str = Field(min_length=10, max_length=200)
    order_id: str = Field(min_length=6, max_length=64)
    amount: int = Field(ge=1)


# ---------------------------------------------------------------- 손님 계정
class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    company: str = Field(default="", max_length=40)
    phone: str = Field(min_length=9, max_length=20)
    password: str = Field(min_length=4, max_length=40)
    address: str = Field(default="", max_length=200)
    zipcode: str = Field(default="", max_length=10)
    agree_privacy: bool

    @field_validator("name", "company", "address", "zipcode", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip()


class LoginIn(BaseModel):
    phone: str = Field(min_length=9, max_length=20)
    password: str = Field(min_length=1, max_length=40)


class ProfileOut(BaseModel):
    name: str
    company: str
    phone: str
    address: str
    zipcode: str


class AuthOut(BaseModel):
    token: str
    profile: ProfileOut


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=30)
    company: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=200)
    zipcode: str | None = Field(default=None, max_length=10)


class PasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=40)
    new_password: str = Field(min_length=4, max_length=40)


class MyLine(BaseModel):
    sku: str
    name: str
    qty: int
    amount: int | None


class MyOrderOut(BaseModel):
    order_id: str
    created_at: str
    status: str
    due_date: str
    ship_method: str
    lines: list[MyLine]
    subtotal: int | None
    shipping_fee: int
    total: int | None
    paid: bool
    recipient: str
    address: str
    carrier: str
    tracking_no: str
    truck_no: str


def _profile(c: CustomerOut) -> ProfileOut:
    if c.type == "B2B":
        return ProfileOut(name=c.contact_name or c.name, company=c.name, phone=c.phone, address=c.address, zipcode=c.zipcode)
    return ProfileOut(name=c.contact_name or c.name, company="", phone=c.phone, address=c.address, zipcode=c.zipcode)


def _attachable(c: CustomerOut) -> bool:
    """손님이 스스로 비밀번호를 걸 수 있는 거래처: 개인 고객이거나 웹 주문서로 생긴 거래처.
    부모님이 등록한 거래처는 번호만 알면 남이 가입해 주문 내역을 볼 수 있으므로 막는다."""
    return c.type == "B2C" or "웹 주문서" in c.memo


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
        self.login_phone_limiter = _Limiter(10, 3600, "비밀번호를 너무 많이 틀렸어요. 1시간 뒤 다시 해 주시거나 전화 주세요.")
        self.login_ip_limiter = _Limiter(30, 3600, "로그인 시도가 너무 많아요. 잠시 뒤 다시 해 주세요.")
        self._done: dict[str, tuple[float, GuestOrderOut]] = {}  # client_token → 결과
        self._place_lock = threading.Lock()

    # ---------------------------------------------------------------- 주문서 정보
    def _visible_products(self) -> list:
        return [p for p in self.ctx.products.list() if p.shop_visible]

    def _min_due(self, st: AppSettings, products: list | None = None) -> date:
        return first_open_day(today() + timedelta(days=lead_for(st, products)), closed_weekdays(st.closed_days))

    def info(self) -> ShopInfo:
        st = self.ctx.settings.load()
        if not st.shop_enabled:
            raise NotFoundError(f"지금은 웹 주문을 받지 않아요. {st.factory_phone or ''}로 연락 주세요.".strip())
        closed = sorted(closed_weekdays(st.closed_days))
        return ShopInfo(
            factory_name=st.factory_name or "주문서",
            factory_phone=st.factory_phone,
            notice=st.shop_notice,
            intro=st.shop_intro,
            contact_hours=st.contact_hours,
            show_prices=st.shop_show_prices,
            bank_account=st.bank_account,
            pay_client_key=self.ctx.config.toss_client_key if self.ctx.config.toss_enabled else "",
            pay_test_mode=self.ctx.config.toss_enabled and self.ctx.config.toss_test_mode,
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
                    sold_out=p.sold_out, image_url=p.image_url, lead_days=lead_for(st, [p]),
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
            min_due = self._min_due(st, [visible[i.sku] for i in body.items])
            if body.due_date < min_due:
                raise ValidationFailed(f"받는 날은 {fmt_date_ko(min_due)}부터 고를 수 있어요. (담으신 품목 준비 기간)")
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

    def place(self, body: GuestOrderIn, client_ip: str = "", token: str = "") -> GuestOrderOut:
        st = self.ctx.settings.load()
        self._validate(body, st)
        phone_d = digits(body.phone)
        member = self.member(token) if token else None
        if body.password and not member and len(body.password) < 4:
            raise ValidationFailed("비밀번호는 4자리 이상으로 만들어 주세요.")

        # 같은 주문서가 두 번 들어오면(두 번 누름·느린 인터넷 재시도) 처음 결과를 그대로 돌려준다
        with self._place_lock:
            cached = self._cached(body.client_token)
            if cached:
                return cached
            self.phone_limiter.check(phone_d)
            if client_ip:
                self.ip_limiter.check(client_ip)

            phone = pretty_phone(phone_d)
            new_token = ""
            if member:
                customer = member  # 로그인 손님: 받는 분·주소가 달라도(선물) 내 주문으로
            else:
                customer = self._find_or_create_customer(body, phone)
                if body.password:
                    new_token = self._set_first_password(customer, body.password)
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
                order = self.ctx.orders.set_fields(
                    order.order_id, {"shipping_fee": None, "order_total": order.total_amount}, publish=None
                )
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
                token=new_token or (token if member else ""),
                pay_token=self._pay_token(order.order_id),
            )
            if body.client_token:
                self._done[body.client_token] = (time.monotonic(), out)
            return out

    # ---------------------------------------------------------------- 손님 계정
    @property
    def _secret(self) -> str:
        return self.ctx.config.auth_secret

    def _rows_by_phone(self, phone: str) -> list[dict]:
        target = digits(phone)
        return [
            d for d in self.ctx.customers.rows(fresh=True)
            if d.get("customer_id") and digits(d.get("phone", "")) == target and d.get("active") is not False
        ]

    def _set_first_password(self, c: CustomerOut, password: str) -> str:
        """주문하면서 가입: 비밀번호가 아직 없고 손님이 걸 수 있는 거래처일 때만. 토큰 또는 ''."""
        row = self.ctx.customers.get(c.customer_id, fresh=True) or {}
        if row.get("web_password") or not _attachable(c):
            return ""
        h = hash_password(password)
        self.ctx.customers.update((c.customer_id,), {"web_password": h})
        self.ctx.logs.write("웹 가입", c.customer_id, c.name, actor="웹주문서")
        return issue_token(self._secret, c.customer_id, h)

    def member(self, token: str) -> CustomerOut:
        """로그인 토큰 → 거래처. 만료·비밀번호 변경·초기화면 다시 로그인하라고 알린다."""
        got = read_token(self._secret, token)
        row = self.ctx.customers.get(got[0], fresh=True) if got else None
        if not got or not row or row.get("active") is False or not token_matches(got[1], row.get("web_password") or ""):
            raise UnauthorizedError("다시 로그인해 주세요.")
        return CustomerOut.from_row(row)

    def signup(self, body: SignupIn) -> AuthOut:
        if not body.agree_privacy:
            raise ValidationFailed("개인정보 수집·이용에 동의해 주셔야 가입할 수 있어요.")
        if not MOBILE_RE.match(digits(body.phone)):
            raise ValidationFailed("휴대폰 번호를 확인해 주세요 (예: 010-1234-5678).")
        phone = pretty_phone(body.phone)
        rows = self._rows_by_phone(phone)
        if any(r.get("web_password") for r in rows):
            raise ValidationFailed("이미 가입된 번호예요. 로그인해 주세요. 비밀번호를 잊었으면 전화 주세요.")
        # 이름 비교·새 거래처 만들기에 쓰는 임시 값 (검사 없이 만든다)
        probe = GuestOrderIn.model_construct(
            name=body.name, company=body.company, phone=phone, address=body.address, zipcode=body.zipcode,
        )
        same = [CustomerOut.from_row(r) for r in rows]
        found = next((x for x in same if _attachable(x) and self._same_person(x, probe)), None)
        if found is None:
            c = self._new_customer(probe, phone, same)
        else:
            c = found
            if body.address:
                self.ctx.customers.update((c.customer_id,), {"address": body.address, "zipcode": body.zipcode})
        h = hash_password(body.password)
        self.ctx.customers.update((c.customer_id,), {"web_password": h, "privacy_agreed_at": now()})
        self.ctx.logs.write("웹 가입", c.customer_id, c.name, actor="웹주문서")
        fresh = CustomerOut.from_row(self.ctx.customers.get(c.customer_id, fresh=True) or {})
        return AuthOut(token=issue_token(self._secret, c.customer_id, h), profile=_profile(fresh))

    def _new_customer(self, body: GuestOrderIn, phone: str, same: list[CustomerOut]) -> CustomerOut:
        existing = [d.get("customer_id") or "" for d in self.ctx.customers.rows()]
        cid = next_seq_id(existing, "C")
        memo = "웹 주문서로 가입"
        if same:
            memo += f" · 확인 필요: 번호가 {', '.join(c.name for c in same)}({', '.join(c.customer_id for c in same)})와 같아요"
        row = {
            "customer_id": cid, "name": body.company or body.name, "aliases": body.name if body.company else "",
            "type": "B2B" if body.company else "B2C", "contact_name": body.name, "phone": phone,
            "address": body.address, "zipcode": body.zipcode, "default_method": "자동", "notify_opt_in": True,
            "privacy_agreed_at": now(), "memo": memo, "active": True,
        }
        self.ctx.customers.insert(row)
        return CustomerOut.from_row(row)

    def login(self, body: LoginIn, client_ip: str = "") -> AuthOut:
        key = digits(body.phone)
        self.login_phone_limiter.check(key)
        if client_ip:
            self.login_ip_limiter.check(client_ip)
        for r in self._rows_by_phone(body.phone):
            h = r.get("web_password") or ""
            if h and check_password(body.password, h):
                return AuthOut(token=issue_token(self._secret, r["customer_id"], h), profile=_profile(CustomerOut.from_row(r)))
        self.login_phone_limiter.hit(key)
        if client_ip:
            self.login_ip_limiter.hit(client_ip)
        raise ValidationFailed("휴대폰 번호나 비밀번호가 맞지 않아요.")

    def me(self, token: str) -> ProfileOut:
        return _profile(self.member(token))

    def update_me(self, token: str, body: ProfilePatch) -> ProfileOut:
        c = self.member(token)
        ch: dict[str, Any] = {}
        if body.name is not None:
            ch["contact_name"] = body.name.strip()
            if c.type == "B2C":
                ch["name"] = body.name.strip()
        if body.company is not None and body.company.strip() and c.type == "B2B":
            ch["name"] = body.company.strip()
        if body.address is not None:
            ch["address"] = body.address.strip()
        if body.zipcode is not None:
            ch["zipcode"] = digits(body.zipcode)
        if ch:
            self.ctx.customers.update((c.customer_id,), ch)
            self.ctx.logs.write("웹 정보 수정", c.customer_id, ", ".join(ch), actor="웹주문서")
        return _profile(CustomerOut.from_row(self.ctx.customers.get(c.customer_id, fresh=True) or {}))

    def change_password(self, token: str, body: PasswordIn) -> AuthOut:
        c = self.member(token)
        row = self.ctx.customers.get(c.customer_id, fresh=True) or {}
        if not check_password(body.old_password, row.get("web_password") or ""):
            raise ValidationFailed("지금 비밀번호가 맞지 않아요.")
        h = hash_password(body.new_password)
        self.ctx.customers.update((c.customer_id,), {"web_password": h})
        return AuthOut(token=issue_token(self._secret, c.customer_id, h), profile=_profile(c))

    def my_orders(self, token: str) -> list[MyOrderOut]:
        c = self.member(token)
        orders = self.ctx.orders.query(customer_id=c.customer_id, include_cancelled=True)
        orders.sort(key=lambda o: o.created_at.isoformat() if o.created_at else "", reverse=True)
        out = []
        for o in orders[:50]:
            out.append(MyOrderOut(
                order_id=o.order_id,
                created_at=o.created_at.strftime("%Y.%m.%d %H:%M") if o.created_at else "",
                status=o.status,
                due_date=fmt_date_ko(o.due_date) if o.due_date else "가장 빠른 날",
                ship_method=o.ship_method,
                lines=[MyLine(sku=l.sku, name=l.product_name, qty=l.qty, amount=l.amount) for l in o.lines],
                subtotal=o.total_amount,
                shipping_fee=o.shipping_fee,
                total=o.total_amount + o.shipping_fee if o.total_amount is not None else None,
                paid=o.paid_at is not None,
                recipient=o.recipient, address=o.address,
                carrier=o.carrier, tracking_no=o.tracking_no, truck_no=o.truck_no,
            ))
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

    # ---------------------------------------------------------------- 온라인 결제 (토스페이먼츠)
    @property
    def _http(self) -> Any:
        from ...integrations.http import http_request

        return getattr(self.ctx, "http", None) or http_request

    def _pay_token(self, order_id: str) -> str:
        return sign(self._secret, f"pay:{order_id}", 3 * 24 * 3600)

    @staticmethod
    def pay_amount(o: OrderOut) -> int | None:
        """결제할 금액 = 품목 금액 + 택배비. 가격이 빈 품목이 있으면 온라인 결제 불가"""
        if o.total_amount is None or o.total_amount <= 0:
            return None
        return o.total_amount + (o.shipping_fee or 0)

    def _payable(self, order_id: str) -> OrderOut:
        cfg = self.ctx.config
        if not cfg.toss_enabled:
            raise ValidationFailed("지금은 온라인 결제를 받지 않아요. 계좌로 입금해 주세요.")
        try:
            o = self.ctx.orders.get((order_id or "").strip().upper())
        except NotFoundError:
            raise NotFoundError("주문을 찾지 못했어요.") from None
        if o.status == "취소":
            raise ValidationFailed("취소된 주문이에요.")
        return o

    def pay_info(self, order_id: str, *, phone_tail: str = "", pay_token: str = "", member_token: str = "",
                 client_ip: str = "") -> PayInfo:
        key = client_ip or "anon"
        self.lookup_limiter.check(key)
        self.lookup_limiter.hit(key)
        o = self._payable(order_id)
        allowed = False
        if pay_token and verify(self._secret, pay_token) == f"pay:{o.order_id}":
            allowed = True
        elif phone_tail and len(digits(phone_tail)) == 4 and digits(o.phone).endswith(digits(phone_tail)):
            allowed = True
        elif member_token:
            try:
                allowed = self.member(member_token).customer_id == o.customer_id
            except Exception:
                allowed = False
        if not allowed:
            raise NotFoundError("주문을 찾지 못했어요.")
        if o.paid_at is not None:
            raise ValidationFailed("이미 결제(입금)된 주문이에요.")
        amount = self.pay_amount(o)
        if amount is None:
            raise ValidationFailed("금액이 아직 정해지지 않은 주문이라 공장에서 확인 후 안내해 드려요.")
        first = o.lines[0].product_name if o.lines else "주문"
        name = first if len(o.lines) <= 1 else f"{first} 외 {len(o.lines) - 1}건"
        cfg = self.ctx.config
        return PayInfo(order_id=o.order_id, order_name=name[:100], amount=amount, customer_name=o.recipient or o.customer_name,
                       client_key=cfg.toss_client_key, test_mode=cfg.toss_test_mode)

    def pay_confirm(self, body: PayConfirmIn) -> PublicOrderOut:
        """결제 승인: 금액을 주문과 맞춰 본 뒤 토스에 승인 요청 → 성공하면 '입금 확인' 처리"""
        o = self._payable(body.order_id)
        if o.paid_at is not None:
            if o.pay_key and o.pay_key == body.payment_key:
                return to_public(o)  # 새로고침 등으로 두 번 온 경우
            raise ValidationFailed("이미 결제(입금)된 주문이에요. 결제가 두 번 됐다면 공장에 연락해 주세요.")
        amount = self.pay_amount(o)
        if amount is None or amount != body.amount:
            # 금액을 바꿔 치기 했거나 주문이 바뀐 경우 — 승인하지 않는다 (인증만 된 결제는 자동 취소됨)
            self.ctx.logs.write("결제 금액 불일치", o.order_id, f"요청 {body.amount}원 / 주문 {amount}원", actor="웹결제")
            raise ValidationFailed("결제 금액이 주문 금액과 달라요. 주문을 다시 확인해 주세요.")
        from ...integrations.toss import TossClient

        res = TossClient(self.ctx.config.toss_secret_key, self._http).confirm(body.payment_key, o.order_id, amount)
        if not res.ok:
            self.ctx.logs.write("결제 실패", o.order_id, res.message, actor="웹결제")
            raise ValidationFailed(f"결제가 완료되지 않았어요. {res.message}")
        method = res.method or "온라인결제"
        lines = self.ctx.orders_repo.lines_of(o.order_id, fresh=True)
        self.ctx.orders_repo.update_many(
            [((o.order_id, l["line_no"]), {"paid_at": now(), "pay_method": method, "pay_key": body.payment_key, "updated_at": now()})
             for l in lines]
        )
        self.ctx.logs.write("온라인 결제", o.order_id, f"{amount:,}원 · {method}", actor=f"웹결제:{o.recipient}")
        out = self.ctx.orders.get(o.order_id, fresh=True)
        self.ctx.bus.publish("order.paid", {"order": out})
        return to_public(out)

    def refund(self, o: OrderOut, actor: str) -> None:
        """주문 취소 전에 온라인 결제를 환불한다. 실패하면 취소도 멈춘다 (돈만 빠지고 취소되는 일 없게)."""
        if not o.pay_key or not o.paid_at or "환불" in o.pay_method:
            return
        if not self.ctx.config.toss_secret_key:
            raise ValidationFailed("온라인 결제 주문인데 결제 키가 없어 환불을 못 했어요. 토스페이먼츠 상점관리자에서 직접 취소해 주세요.")
        from ...integrations.toss import TossClient

        res = TossClient(self.ctx.config.toss_secret_key, self._http).cancel(o.pay_key, f"주문 취소 ({actor})")
        if not res.ok:
            raise ValidationFailed(f"카드 결제 환불이 안 됐어요: {res.message} — 토스페이먼츠 상점관리자에서 확인해 주세요.")
        lines = self.ctx.orders_repo.lines_of(o.order_id, fresh=True)
        self.ctx.orders_repo.update_many([((o.order_id, l["line_no"]), {"pay_method": f"{o.pay_method} (환불)"}) for l in lines])
        self.ctx.logs.write("결제 환불", o.order_id, f"{(self.pay_amount(o) or 0):,}원", actor=actor)

