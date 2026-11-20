from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ...api.deps import get_ctx, require_admin
from ...context import AppContext
from ...core.errors import ValidationFailed
from ...core.signing import sign, verify
from ...integrations.kakao import KakaoError
from .report import BriefingOut

router = APIRouter(prefix="/api", tags=["briefing"])
admin = [Depends(require_admin)]


# ------------------------------------------------------------------ 브리핑
@router.get("/briefing/preview", response_model=BriefingOut, dependencies=admin)
def preview(ctx: AppContext = Depends(get_ctx)) -> BriefingOut:
    return ctx.services["briefing"].preview()


@router.post("/briefing/send", dependencies=admin)
def send_now(ctx: AppContext = Depends(get_ctx)) -> dict:
    return ctx.services["briefing"].send(force=True)


# ------------------------------------------------------------------ 카카오 연결
class KakaoStatusOut(BaseModel):
    configured: bool
    connected: bool
    nickname: str = ""
    connected_at: str | None = None
    refresh_expires_at: str | None = None
    redirect_uri: str


@router.get("/integrations/kakao/status", response_model=KakaoStatusOut, dependencies=admin)
def kakao_status(ctx: AppContext = Depends(get_ctx)) -> KakaoStatusOut:
    return KakaoStatusOut(**ctx.kakao.status(), redirect_uri=ctx.config.kakao_callback_url)


@router.post("/integrations/kakao/login-url", dependencies=admin)
def kakao_login_url(ctx: AppContext = Depends(get_ctx)) -> dict:
    if not ctx.kakao.configured:
        raise ValidationFailed("KAKAO_REST_API_KEY 를 먼저 설정해 주세요.")
    state = sign(ctx.config.auth_secret, "kakao-connect", ttl_sec=600)
    return {"url": ctx.kakao.authorize_url(state)}


@router.get("/integrations/kakao/callback", include_in_schema=False)
def kakao_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = Query(default=""),
    ctx: AppContext = Depends(get_ctx),
) -> RedirectResponse:
    """카카오가 돌려보내는 주소. 로그인 토큰이 없으므로 state 서명으로 우리가 시작한 요청인지 확인한다."""
    back = f"{ctx.config.public_web_url}/settings?tab=kakao"
    if error:
        return RedirectResponse(f"{back}&kakao=fail&msg={quote(error_description or error)}")
    if verify(ctx.config.auth_secret, state) != "kakao-connect":
        return RedirectResponse(f"{back}&kakao=fail&msg={quote('연결 요청이 만료됐어요. 다시 눌러 주세요.')}")
    try:
        info = ctx.kakao.exchange_code(code)
    except KakaoError as e:
        return RedirectResponse(f"{back}&kakao=fail&msg={quote(str(e))}")
    ctx.logs.write("카카오 연결", "kakao", info.get("nickname", ""))
    ctx.notifier.send("연결확인", "✅ 공장 도우미와 카카오톡이 연결됐어요.\n매일 아침 브리핑과 재고 경고가 이 채팅방으로 와요.")
    return RedirectResponse(f"{back}&kakao=ok")


@router.post("/integrations/kakao/test", dependencies=admin)
def kakao_test(ctx: AppContext = Depends(get_ctx)) -> dict:
    ok = ctx.notifier.send("테스트", "🔔 테스트 메시지예요. 잘 보이면 연결 완료!")
    if not ok:
        last = ctx.messages.recent(1)
        raise ValidationFailed((last[0].get("error") if last else "") or "카카오 발송에 실패했어요.")
    return {"sent": True}


@router.post("/integrations/kakao/refresh", dependencies=admin)
def kakao_refresh(ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        return ctx.kakao.refresh()
    except KakaoError as e:
        raise ValidationFailed(str(e)) from e


@router.post("/integrations/kakao/disconnect", status_code=204, dependencies=admin)
def kakao_disconnect(ctx: AppContext = Depends(get_ctx)) -> None:
    ctx.kakao.disconnect()
    ctx.logs.write("카카오 연결 해제", "kakao")


# ------------------------------------------------------------------ 발송 기록
class MessageOut(BaseModel):
    ts: str
    channel: str
    kind: str
    to: str
    order_id: str
    result: str
    content: str
    error: str


@router.get("/messages", response_model=list[MessageOut], dependencies=admin)
def messages(limit: int = Query(default=100, le=500), order_id: str = "", ctx: AppContext = Depends(get_ctx)) -> list[MessageOut]:
    rows = ctx.messages.recent(limit, order_id or None)
    return [
        MessageOut(
            ts=r["ts"].strftime("%Y-%m-%d %H:%M") if r.get("ts") else "",
            channel=r.get("channel", ""), kind=r.get("kind", ""), to=r.get("to", ""),
            order_id=r.get("order_id", ""), result=r.get("result", ""), content=r.get("content", ""),
            error=r.get("error", ""),
        )
        for r in rows
    ]
