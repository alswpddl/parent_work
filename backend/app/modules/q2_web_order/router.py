from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...api.deps import get_ctx
from ...context import AppContext
from ..q2_self_order.service import PublicOrderOut
from .service import GuestOrderIn, GuestOrderOut, ShopInfo

router = APIRouter(prefix="/api/public/shop", tags=["public"])


def client_ip(request: Request) -> str:
    """Render 같은 프록시 뒤에서는 X-Forwarded-For 첫 번째 값이 실제 접속 주소."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.get("", response_model=ShopInfo)
def shop_info(ctx: AppContext = Depends(get_ctx)) -> ShopInfo:
    return ctx.services["web_order"].info()


@router.post("/orders", response_model=GuestOrderOut, status_code=201)
def place_order(body: GuestOrderIn, request: Request, ctx: AppContext = Depends(get_ctx)) -> GuestOrderOut:
    return ctx.services["web_order"].place(body, client_ip(request))


@router.get("/orders/lookup", response_model=PublicOrderOut)
def lookup(
    request: Request,
    order_id: str = Query(min_length=5, max_length=30),
    phone4: str = Query(min_length=4, max_length=4),
    ctx: AppContext = Depends(get_ctx),
) -> PublicOrderOut:
    return ctx.services["web_order"].lookup(order_id, phone4, client_ip(request))
