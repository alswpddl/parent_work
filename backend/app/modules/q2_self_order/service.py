"""거래처 셀프 주문 — 로그인 없이 '거래처별 비밀 링크'로 들어와 주문한다.

- 링크 토큰은 거래처 탭의 '주문링크토큰' 열에 저장. 재발급하면 이전 링크는 바로 막힌다.
- 토큰당 1시간에 주문 10건까지 (장난 방지).
- 들어온 주문은 일반 주문과 똑같이 주문장에 쌓이고, 경로는 '셀프주문'.
"""

from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from ...core.errors import NotFoundError, TooManyRequests, ValidationFailed
from ...core.ids import random_token
from ...core.timeutil import fmt_date_ko, today
from ...schemas.customer import CustomerOut
from ...schemas.order import OrderCreate, OrderItemIn, OrderOut


# ---------------------------------------------------------------- 입출력 모델
class LinkOut(BaseModel):
    customer_id: str
    url: str
    token: str


class FormProduct(BaseModel):
    sku: str
    name: str
    spec: str
    unit: str
    display_name: str


class FormFavorite(BaseModel):
    sku: str
    qty: int


class OrderFormOut(BaseModel):
    customer_name: str
    address: str
    notice: str
    min_due_date: date
    products: list[FormProduct]
    last_items: list[FormFavorite]  # '지난번처럼' 버튼용


class SelfOrderIn(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1, max_length=30)
    due_date: date | None = None
    note: str = Field(default="", max_length=300)
    address: str = Field(default="", max_length=200, description="비우면 거래처 기본 배송지")


class PublicOrderOut(BaseModel):
    order_id: str
    created_at: str
    status: str
    due_date: str
    items: str
    ship_method: str
    carrier: str = ""
    tracking_no: str = ""
    truck_no: str = ""


def to_public(o: OrderOut) -> PublicOrderOut:
    return PublicOrderOut(
        order_id=o.order_id,
        created_at=o.created_at.strftime("%m/%d %H:%M") if o.created_at else "",
        status=o.status,
        due_date=fmt_date_ko(o.due_date),
        items=", ".join(f"{l.product_name} {l.qty}" for l in o.lines),
        ship_method=o.ship_method,
        carrier=o.carrier,
        tracking_no=o.tracking_no,
        truck_no=o.truck_no,
    )


class _Limiter:
    def __init__(self, n: int, window: int):
        self.n, self.window = n, window
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def hit(self, key: str) -> None:
        t = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and t - q[0] > self.window:
                q.popleft()
            if len(q) >= self.n:
                raise TooManyRequests("주문이 너무 많이 들어왔어요. 잠시 뒤 다시 해 주시거나 전화 주세요.")
            q.append(t)


class SelfOrderService:
    def __init__(self, ctx: Any):
        self.ctx = ctx
        self.order_limiter = _Limiter(10, 3600)

    # ---------------------------------------------------------------- 관리자
    def link_url(self, token: str) -> str:
        return f"{self.ctx.config.public_web_url}/order/{token}"

    def issue_link(self, customer_id: str, regenerate: bool = False) -> LinkOut:
        row = self.ctx.customers.get(customer_id, fresh=True)
        if not row:
            raise NotFoundError("거래처를 찾을 수 없어요.")
        token = row.get("order_token") or ""
        if regenerate or not token:
            token = random_token()
            self.ctx.customers.update((customer_id,), {"order_token": token})
            self.ctx.logs.write("주문링크 발급", customer_id, row.get("name", ""))
        return LinkOut(customer_id=customer_id, url=self.link_url(token), token=token)

    def revoke_link(self, customer_id: str) -> None:
        if not self.ctx.customers.get(customer_id, fresh=True):
            raise NotFoundError("거래처를 찾을 수 없어요.")
        self.ctx.customers.update((customer_id,), {"order_token": ""})
        self.ctx.logs.write("주문링크 해지", customer_id)

    # ---------------------------------------------------------------- 공개
    def customer_by_token(self, token: str) -> CustomerOut:
        token = (token or "").strip()
        if len(token) < 16:
            raise NotFoundError("주문 링크가 올바르지 않아요. 공장에 새 링크를 요청해 주세요.")
        for d in self.ctx.customers.rows():
            saved = d.get("order_token") or ""
            if saved and hmac.compare_digest(saved, token):
                c = CustomerOut.from_row(d)
                if not c.active:
                    break
                return c
        raise NotFoundError("주문 링크가 만료됐어요. 공장에 새 링크를 요청해 주세요.")

    def form(self, token: str) -> OrderFormOut:
        c = self.customer_by_token(token)
        st = self.ctx.settings.load()
        products = [
            FormProduct(sku=p.sku, name=p.name, spec=p.spec, unit=p.unit, display_name=p.display_name)
            for p in self.ctx.products.list()
        ]
        active_skus = {p.sku for p in products}
        last = self.ctx.orders.query(customer_id=c.customer_id)
        last_items: list[FormFavorite] = []
        if last:
            newest = max(last, key=lambda o: o.created_at.isoformat() if o.created_at else "")
            last_items = [FormFavorite(sku=l.sku, qty=l.qty) for l in newest.lines if l.sku in active_skus]
        return OrderFormOut(
            customer_name=c.name,
            address=c.address,
            notice=st.self_order_notice,
            min_due_date=today() + timedelta(days=st.self_order_lead_days),
            products=products,
            last_items=last_items,
        )

    def place(self, token: str, body: SelfOrderIn) -> PublicOrderOut:
        c = self.customer_by_token(token)
        self.order_limiter.hit(token)
        st = self.ctx.settings.load()
        min_due = today() + timedelta(days=st.self_order_lead_days)
        if body.due_date and body.due_date < min_due:
            raise ValidationFailed(f"받는 날짜는 {fmt_date_ko(min_due)} 이후로 골라 주세요.")
        order = self.ctx.orders.create(
            OrderCreate(
                customer_id=c.customer_id,
                items=body.items,
                due_date=body.due_date,
                note=body.note.strip(),
                address=body.address.strip(),
                source="셀프주문",
            ),
            actor=f"거래처:{c.name}",
        )
        return to_public(order)

    def recent(self, token: str, limit: int = 5) -> list[PublicOrderOut]:
        c = self.customer_by_token(token)
        orders = self.ctx.orders.query(customer_id=c.customer_id, include_cancelled=True)
        orders.sort(key=lambda o: o.created_at.isoformat() if o.created_at else "", reverse=True)
        return [to_public(o) for o in orders[:limit]]

    # ---------------------------------------------------------------- 이벤트
    def on_order_created(self, payload: dict) -> None:
        o: OrderOut = payload["order"]
        if o.source not in ("셀프주문", "웹주문서"):
            return
        if not self.ctx.settings.load().notify_new_self_order:
            return
        items = ", ".join(f"{l.product_name} {l.qty}" for l in o.lines)
        text = (
            f"🛒 새 {'웹 주문' if o.source == '웹주문서' else '셀프주문'}\n{o.customer_name}"
            + (f" ({o.recipient})" if o.recipient and o.recipient != o.customer_name else "")
            + f"\n{items}\n"
            f"납기 {fmt_date_ko(o.due_date)} · {o.ship_method} · {o.order_kg:g}kg"
            + (f"\n메모: {o.note}" if o.note else "")
        )
        self.ctx.notifier.send("셀프주문", text, path="/orders", button="주문 보기")
