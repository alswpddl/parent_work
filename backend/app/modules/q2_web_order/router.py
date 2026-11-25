from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request

from ...api.deps import get_ctx
from ...context import AppContext
from ..q2_self_order.service import PublicOrderOut
from .service import (
    AuthOut,
    GuestOrderIn,
    GuestOrderOut,
    LoginIn,
    MyOrderOut,
    PasswordIn,
    ProfileOut,
    ProfilePatch,
    ShopInfo,
    SignupIn,
)

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
def place_order(
    body: GuestOrderIn, request: Request, x_shop_token: str = Header(default=""), ctx: AppContext = Depends(get_ctx)
) -> GuestOrderOut:
    """비회원 주문 (로그인 손님이면 X-Shop-Token 헤더로 내 주문에 묶임)"""
    return ctx.services["web_order"].place(body, client_ip(request), x_shop_token)


# ---------------------------------------------------------------- 손님 계정 (휴대폰 + 비밀번호)
@router.post("/auth/signup", response_model=AuthOut, status_code=201)
def signup(body: SignupIn, ctx: AppContext = Depends(get_ctx)) -> AuthOut:
    return ctx.services["web_order"].signup(body)


@router.post("/auth/login", response_model=AuthOut)
def login(body: LoginIn, request: Request, ctx: AppContext = Depends(get_ctx)) -> AuthOut:
    return ctx.services["web_order"].login(body, client_ip(request))


@router.get("/me", response_model=ProfileOut)
def me(x_shop_token: str = Header(default=""), ctx: AppContext = Depends(get_ctx)) -> ProfileOut:
    return ctx.services["web_order"].me(x_shop_token)


@router.patch("/me", response_model=ProfileOut)
def update_me(body: ProfilePatch, x_shop_token: str = Header(default=""), ctx: AppContext = Depends(get_ctx)) -> ProfileOut:
    return ctx.services["web_order"].update_me(x_shop_token, body)


@router.post("/me/password", response_model=AuthOut)
def change_password(body: PasswordIn, x_shop_token: str = Header(default=""), ctx: AppContext = Depends(get_ctx)) -> AuthOut:
    return ctx.services["web_order"].change_password(x_shop_token, body)


@router.get("/me/orders", response_model=list[MyOrderOut])
def my_orders(x_shop_token: str = Header(default=""), ctx: AppContext = Depends(get_ctx)) -> list[MyOrderOut]:
    return ctx.services["web_order"].my_orders(x_shop_token)


@router.get("/orders/lookup", response_model=PublicOrderOut)
def lookup(
    request: Request,
    order_id: str = Query(min_length=5, max_length=30),
    phone4: str = Query(min_length=4, max_length=4),
    ctx: AppContext = Depends(get_ctx),
) -> PublicOrderOut:
    return ctx.services["web_order"].lookup(order_id, phone4, client_ip(request))
