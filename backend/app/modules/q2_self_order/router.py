from __future__ import annotations

from fastapi import APIRouter, Depends

from ...api.deps import get_ctx, require_admin
from ...context import AppContext
from .service import LinkOut, OrderFormOut, PublicOrderOut, SelfOrderIn, SelfOrderService

admin_router = APIRouter(prefix="/api", tags=["self-order"], dependencies=[Depends(require_admin)])
public_router = APIRouter(prefix="/api/public", tags=["public"])


def _svc(ctx: AppContext) -> SelfOrderService:
    return ctx.services["self_order"]


@admin_router.post("/customers/{customer_id}/order-link", response_model=LinkOut)
def issue_link(customer_id: str, regenerate: bool = False, ctx: AppContext = Depends(get_ctx)) -> LinkOut:
    """거래처 전용 주문 링크. regenerate=true 면 새 링크를 만들고 이전 링크는 막는다."""
    return _svc(ctx).issue_link(customer_id, regenerate)


@admin_router.delete("/customers/{customer_id}/order-link", status_code=204)
def revoke_link(customer_id: str, ctx: AppContext = Depends(get_ctx)) -> None:
    _svc(ctx).revoke_link(customer_id)


@public_router.get("/order-form/{token}", response_model=OrderFormOut)
def order_form(token: str, ctx: AppContext = Depends(get_ctx)) -> OrderFormOut:
    return _svc(ctx).form(token)


@public_router.post("/orders/{token}", response_model=PublicOrderOut, status_code=201)
def place_order(token: str, body: SelfOrderIn, ctx: AppContext = Depends(get_ctx)) -> PublicOrderOut:
    return _svc(ctx).place(token, body)


@public_router.get("/orders/{token}", response_model=list[PublicOrderOut])
def recent_orders(token: str, ctx: AppContext = Depends(get_ctx)) -> list[PublicOrderOut]:
    return _svc(ctx).recent(token)
