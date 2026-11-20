"""FastAPI 의존성: 컨텍스트 주입과 인증."""

from __future__ import annotations

from fastapi import Header, Request

from ..context import AppContext
from ..core.auth import check_job_secret, verify_admin_token
from ..core.errors import UnauthorizedError


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def require_admin(request: Request, authorization: str | None = Header(default=None)) -> dict:
    ctx: AppContext = request.app.state.ctx
    # 개발 편의: PIN 이 설정되지 않은 dev 환경에서는 인증 생략
    if ctx.config.app_env != "prod" and not ctx.config.admin_pin:
        return {"sub": "admin", "role": "admin", "dev": True}
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError()
    return verify_admin_token(ctx.config.auth_secret, authorization.split(" ", 1)[1].strip())


def require_job_secret(request: Request, x_job_secret: str | None = Header(default=None)) -> None:
    ctx: AppContext = request.app.state.ctx
    if not check_job_secret(ctx.config.job_secret, x_job_secret):
        raise UnauthorizedError("작업 비밀키가 맞지 않아요.")
