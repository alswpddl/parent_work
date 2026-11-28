from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import RedirectResponse

from ...api.deps import get_ctx, require_admin
from ...core.errors import AppError
from ...context import AppContext
from ..q2_self_order.service import PublicOrderOut
from .service import (
    PayConfirmIn,
    PayInfo,
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

from .extras import CancelIn, KakaoCompleteIn, ReviewAdminOut, ReviewIn, ReviewList, ReviewOut

router = APIRouter(prefix="/api/public/shop", tags=["public"])
admin_router = APIRouter(prefix="/api/reviews", tags=["reviews"], dependencies=[Depends(require_admin)])


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


# ---------------------------------------------------------------- 온라인 결제 (토스페이먼츠)
@router.get("/pay/{order_id}", response_model=PayInfo)
def pay_info(
    order_id: str,
    request: Request,
    phone: str = Query("", description="받는 분 전화번호 뒤 4자리"),
    pay_token: str = Query("", description="주문 완료 화면에서 받은 결제 표"),
    x_shop_token: str = Header(default=""),
    ctx: AppContext = Depends(get_ctx),
) -> PayInfo:
    return ctx.services["web_order"].pay_info(order_id, phone_tail=phone, pay_token=pay_token, member_token=x_shop_token,
                              client_ip=client_ip(request))


@router.post("/pay/confirm", response_model=PublicOrderOut)
def pay_confirm(body: PayConfirmIn, ctx: AppContext = Depends(get_ctx)) -> PublicOrderOut:
    """결제창 인증 성공 → 금액 확인 → 토스 승인 → 입금 확인 처리 (시간이 걸려 동기 함수)"""
    return ctx.services["web_order"].pay_confirm(body)


# ---------------------------------------------------------------- 손님 직접 취소
@router.post("/orders/cancel", response_model=PublicOrderOut)
def cancel_order(body: CancelIn, request: Request, x_shop_token: str = Header(default=""),
                 ctx: AppContext = Depends(get_ctx)) -> PublicOrderOut:
    """포장 전(주문 접수) 주문만. 로그인 손님은 토큰, 비회원은 전화 뒤 4자리"""
    return ctx.services["web_order"].cancel_by_customer(body, token=x_shop_token, client_ip=client_ip(request))


# ---------------------------------------------------------------- 구매 후기
@router.get("/reviews", response_model=ReviewList)
def reviews(name: str = Query(..., max_length=60), ctx: AppContext = Depends(get_ctx)) -> ReviewList:
    return ctx.services["web_order"].list_reviews(name)


@router.post("/reviews", response_model=ReviewOut, status_code=201)
def write_review(body: ReviewIn, request: Request, x_shop_token: str = Header(default=""),
                 ctx: AppContext = Depends(get_ctx)) -> ReviewOut:
    return ctx.services["web_order"].write_review(body, token=x_shop_token, client_ip=client_ip(request))


@admin_router.get("", response_model=list[ReviewAdminOut])
def admin_reviews(ctx: AppContext = Depends(get_ctx)) -> list[ReviewAdminOut]:
    return ctx.services["web_order"].admin_reviews()


@admin_router.patch("/{review_id}", response_model=ReviewAdminOut)
def hide_review(review_id: str, hidden: bool = Query(...), ctx: AppContext = Depends(get_ctx)) -> ReviewAdminOut:
    return ctx.services["web_order"].hide_review(review_id, hidden)


# ---------------------------------------------------------------- 카카오 로그인
def _web(ctx: AppContext) -> str:
    return (ctx.config.public_web_url or "").rstrip("/")


@router.get("/auth/kakao/start", include_in_schema=False)
def kakao_start(ctx: AppContext = Depends(get_ctx)) -> RedirectResponse:
    try:
        return RedirectResponse(ctx.services["web_order"].kakao_start_url(), status_code=302)
    except AppError as e:
        return RedirectResponse(f"{_web(ctx)}/shop/my#kerr={quote(str(e))}", status_code=302)


@router.get("/auth/kakao/callback", include_in_schema=False)
def kakao_callback(code: str = "", state: str = "", error: str = "", ctx: AppContext = Depends(get_ctx)) -> RedirectResponse:
    """카카오가 돌려보내는 곳 → 결과를 주소 # 뒤에 붙여 웹 주문서 마이페이지로 (서버 기록에 안 남게)"""
    web = _web(ctx)
    if error or not code:
        return RedirectResponse(f"{web}/shop/my#kerr={quote('카카오 로그인을 취소했어요.')}", status_code=302)
    try:
        r = ctx.services["web_order"].kakao_callback(code, state)
    except AppError as e:
        return RedirectResponse(f"{web}/shop/my#kerr={quote(str(e))}", status_code=302)
    if r.token:
        return RedirectResponse(f"{web}/shop/my#kt={quote(r.token)}", status_code=302)
    return RedirectResponse(f"{web}/shop/my#kn={quote(r.ticket)}&nick={quote(r.nickname)}", status_code=302)


@router.post("/auth/kakao/complete", response_model=AuthOut, status_code=201)
def kakao_complete(body: KakaoCompleteIn, ctx: AppContext = Depends(get_ctx)) -> AuthOut:
    return ctx.services["web_order"].kakao_complete(body)

