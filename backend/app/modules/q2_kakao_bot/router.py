from __future__ import annotations

import hmac
import logging

from typing import Any

from fastapi import APIRouter, Body, Depends, Query

from ...api.deps import get_ctx
from ...context import AppContext
from ...core.errors import NotFoundError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kakao", tags=["kakao-bot"])


# 일반 def → FastAPI 가 스레드에서 돌려서, 시트·AI 를 기다리는 동안 다른 요청이 막히지 않는다
@router.post("/skill")
def skill(
    payload: dict[str, Any] = Body(default_factory=dict),
    key: str = Query(default=""),
    ctx: AppContext = Depends(get_ctx),
) -> dict:
    """카카오 챗봇 관리자센터 → 스킬 URL: {PUBLIC_API_URL}/api/kakao/skill?key={KAKAO_SKILL_KEY}"""
    secret = ctx.config.kakao_skill_key
    if not secret or not hmac.compare_digest(key, secret):
        raise NotFoundError("없는 주소예요.")
    bot = ctx.services["kakao_bot"]
    try:
        return bot.answer(payload)
    except Exception:  # noqa: BLE001 — 카카오에는 항상 정상 응답을 준다
        log.exception("kakao skill failed")
        return bot.sorry()
