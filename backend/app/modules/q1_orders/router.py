from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ...api.deps import get_ctx, require_admin
from ...context import AppContext
from ...schemas.order import (
    OrderCreate,
    OrderDraft,
    OrderListOut,
    OrderOut,
    OrderPatch,
    ParseRequest,
    ProductionSummary,
)
from .parser import parse_order_text

router = APIRouter(prefix="/api", tags=["orders"], dependencies=[Depends(require_admin)])


@router.post("/orders/parse", response_model=OrderDraft)
def parse_order(body: ParseRequest, ctx: AppContext = Depends(get_ctx)) -> OrderDraft:
    """카톡 원문 → 확인용 초안. 시트에는 아직 저장하지 않는다."""
    customers = ctx.customers.list()
    products = ctx.products.list()
    parsed, parser, warnings = parse_order_text(body.text, customers, products, ctx.claude, use_ai=body.use_ai)
    return ctx.orders.build_draft(parsed, parser=parser, warnings=warnings, raw_text=body.text)


@router.post("/orders", response_model=OrderOut, status_code=201)
def create_order(body: OrderCreate, ctx: AppContext = Depends(get_ctx)) -> OrderOut:
    return ctx.orders.create(body)


@router.get("/orders", response_model=OrderListOut)
def list_orders(
    status: str = Query(default="", description="쉼표 구분 (예: 접수,출고대기). 비우면 취소 제외 전체"),
    method: str = Query(default="", pattern="^(|택배|화물)$"),
    due_from: date | None = None,
    due_to: date | None = None,
    customer_id: str = "",
    include_cancelled: bool = False,
    ctx: AppContext = Depends(get_ctx),
) -> OrderListOut:
    statuses = [s.strip() for s in status.split(",") if s.strip()] or None
    orders = ctx.orders.query(
        statuses=statuses,
        method=method or None,
        due_from=due_from,
        due_to=due_to,
        customer_id=customer_id or None,
        include_cancelled=include_cancelled,
    )
    return OrderListOut(orders=orders, count=len(orders))


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: str, ctx: AppContext = Depends(get_ctx)) -> OrderOut:
    return ctx.orders.get(order_id)


@router.patch("/orders/{order_id}", response_model=OrderOut)
def patch_order(order_id: str, body: OrderPatch, ctx: AppContext = Depends(get_ctx)) -> OrderOut:
    return ctx.orders.update(order_id, body)


class PaidIn(BaseModel):
    paid: bool = True


@router.post("/orders/{order_id}/paid", response_model=OrderOut)
def set_paid(order_id: str, body: PaidIn, ctx: AppContext = Depends(get_ctx)) -> OrderOut:
    """입금 확인 표시 (paid=false 면 취소)"""
    return ctx.orders.set_paid(order_id, body.paid)


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
def cancel_order(order_id: str, ctx: AppContext = Depends(get_ctx)) -> OrderOut:
    return ctx.orders.cancel(order_id)


@router.get("/production/summary", response_model=ProductionSummary)
def production_summary(
    until: date | None = Query(default=None, description="이 날짜까지 납기인 미출고 주문 (비우면 전체)"),
    ctx: AppContext = Depends(get_ctx),
) -> ProductionSummary:
    return ctx.orders.production_summary(until)
