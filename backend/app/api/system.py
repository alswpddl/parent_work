"""공통 엔드포인트: 상태 확인, 켜진 기능 목록, 로그인, 정기작업 트리거."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..context import AppContext
from ..core.auth import check_pin, issue_admin_token
from ..core.errors import UnauthorizedError
from ..core.timeutil import now
from .deps import get_ctx, require_admin, require_job_secret

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(ctx: AppContext = Depends(get_ctx)) -> dict:
    """서버 깨우기용 (GitHub Actions / 프론트 첫 화면). 시트는 건드리지 않는다."""
    return {"ok": True, "time": now().isoformat(), "backend": ctx.sheets.backend.name}


class FeatureOut(BaseModel):
    name: str
    title: str
    quarter: int


class IntegrationsOut(BaseModel):
    ai: bool
    kakao: bool
    solapi: bool
    email: bool
    toss: bool = False  # 토스페이먼츠 온라인 결제
    toss_test: bool = False  # 테스트 키 (실제 돈은 안 빠짐)


class FeaturesOut(BaseModel):
    modules: list[FeatureOut]
    ai_parser: bool
    auth_required: bool
    env: str
    integrations: IntegrationsOut
    public_web_url: str


@router.get("/system/features", response_model=FeaturesOut)
def features(request: Request, ctx: AppContext = Depends(get_ctx)) -> FeaturesOut:
    specs = request.app.state.modules
    return FeaturesOut(
        modules=[FeatureOut(name=s.name, title=s.title, quarter=s.quarter) for s in specs],
        ai_parser=ctx.claude.enabled,
        auth_required=bool(ctx.config.admin_pin) or ctx.config.app_env == "prod",
        env=ctx.config.app_env,
        integrations=IntegrationsOut(
            ai=ctx.claude.enabled,
            kakao=ctx.kakao.configured,
            solapi=ctx.solapi.configured,
            email=ctx.mailer.configured,
            toss=ctx.config.toss_enabled,
            toss_test=ctx.config.toss_enabled and ctx.config.toss_test_mode,
        ),
        public_web_url=ctx.config.public_web_url,
    )


class PinIn(BaseModel):
    pin: str = Field(min_length=1, max_length=32)


class TokenOut(BaseModel):
    token: str
    expires_at: datetime


@router.post("/auth/pin", response_model=TokenOut)
def login(body: PinIn, request: Request, ctx: AppContext = Depends(get_ctx)) -> TokenOut:
    ip = request.client.host if request.client else "unknown"
    ctx.login_limiter.check(ip)
    if not check_pin(ctx.config.admin_pin, body.pin):
        ctx.login_limiter.fail(ip)
        raise UnauthorizedError("비밀번호가 맞지 않아요.")
    ctx.login_limiter.reset(ip)
    token, exp = issue_admin_token(ctx.config.auth_secret, ctx.config.token_ttl_hours)
    return TokenOut(token=token, expires_at=exp)


@router.get("/system/status", dependencies=[Depends(require_admin)])
def status(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {
        "startup": ctx.startup_report,
        "jobs": [
            {"name": j.name, "cron": j.cron, "module": j.module, "description": j.description,
             "last_run_at": j.last_run_at, "last_result": j.last_result}
            for j in ctx.jobs.list()
        ],
        "config_problems": ctx.config.check_production(),
        "integration_warnings": ctx.config.integration_warnings(),
        "modules": ctx.enabled_modules,
        "sheets_backend": ctx.sheets.backend.name,
        "google": google_info(ctx),
        "kakao_bot": {
            "enabled": bool(ctx.config.kakao_skill_key) and "kakao_bot" in ctx.services,
            # 관리자만 보는 화면이라 비밀 키가 들어간 주소를 그대로 보여 준다 (챗봇 관리자센터에 붙여넣기용)
            "skill_url": f"{ctx.config.public_api_url.rstrip('/')}/api/kakao/skill?key={ctx.config.kakao_skill_key}"
            if ctx.config.kakao_skill_key else "",
        },
    }


def _sheet_url(sid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else ""


def google_info(ctx: AppContext) -> dict:
    """구글 시트 연결 정보 (화면 [상태] 탭에 표시). 비밀 키 내용은 절대 내보내지 않는다."""
    sa = ctx.config.service_account_info or {}
    return {
        "connected": ctx.sheets.backend.name == "gspread",
        "service_account_email": sa.get("client_email", ""),
        "spreadsheet_url": _sheet_url(ctx.config.spreadsheet_id),
        "system_spreadsheet_url": _sheet_url(ctx.config.system_spreadsheet_id),
    }


@router.post("/system/google/check", dependencies=[Depends(require_admin)])
def google_check(ctx: AppContext = Depends(get_ctx)) -> dict:
    """시트를 실제로 한 번 읽어 본다. 실패 이유를 한국어로 돌려준다."""
    if ctx.sheets.backend.name != "gspread":
        return {"ok": False, "message": "지금은 연습용 메모리 모드예요. Render 에 SHEETS_BACKEND=gspread 와 시트 정보를 넣어 주세요."}
    try:
        tabs = ctx.sheets.backend.list_tabs()
        ctx.settings.rows(fresh=True)
    except Exception as e:  # noqa: BLE001 — 어떤 오류든 화면에 이유를 보여 준다
        return {"ok": False, "message": f"시트를 읽지 못했어요: {getattr(e, 'message', None) or e}"}
    return {"ok": True, "message": f"구글 시트와 잘 연결돼 있어요. 탭 {len(tabs)}개: {', '.join(tabs)}"}


@router.post("/jobs/{job_name}", dependencies=[Depends(require_job_secret)])
def run_job(job_name: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return ctx.jobs.run(job_name, ctx)
