"""FastAPI 진입점.

실행
  개발:  uvicorn app.main:app --reload --port 8000
  운영:  uvicorn app.main:app --host 0.0.0.0 --port $PORT   (render.yaml 참고)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .api import system
from .config import AppConfig
from .context import AppContext, bootstrap, build_context
from .core.errors import AppError
from .core.sheets import SheetBackend
from .integrations.claude_client import ClaudeClient
from .modules import load_modules

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

_FIELD_KO = {
    "text": "주문 내용", "items": "품목", "qty": "수량", "sku": "품목", "name": "이름",
    "pin": "비밀번호", "due_date": "납기일", "unit_kg": "개당중량",
}


def create_app(
    config: AppConfig | None = None,
    *,
    backend: SheetBackend | None = None,
    claude: ClaudeClient | None = None,
) -> FastAPI:
    config = config or AppConfig.from_env()
    problems = config.check_production()
    if problems:
        raise RuntimeError("운영 설정 문제:\n- " + "\n- ".join(problems))

    ctx: AppContext = build_context(config, backend=backend, claude=claude)
    specs = load_modules(config.enabled_modules)
    ctx.enabled_modules = [s.name for s in specs]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bootstrap(ctx)
        if config.enable_internal_scheduler:
            ctx.jobs.start_internal_scheduler(ctx)
        log.info("모듈: %s / AI 파서: %s / 시트: %s", ctx.enabled_modules, ctx.claude.enabled, ctx.sheets.backend.name)
        yield
        ctx.jobs.shutdown()

    app = FastAPI(title="공장 주문·출고 도우미 API", version=__version__, lifespan=lifespan)
    app.state.ctx = ctx
    app.state.modules = specs

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.frontend_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Order-Count"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = [str(x) for x in first.get("loc", []) if x not in ("body", "query", "path")]
        field = _FIELD_KO.get(loc[-1], loc[-1]) if loc else "입력값"
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation",
                "message": f"{field}을(를) 확인해 주세요.",
                "detail": jsonable_encoder(exc.errors(), custom_encoder={Exception: str}),
            },
        )

    @app.exception_handler(Exception)
    async def _unknown_error(_: Request, exc: Exception):
        log.exception("처리되지 않은 오류")
        return JSONResponse(status_code=500, content={"error": "server", "message": "잠깐 문제가 생겼어요. 다시 눌러 주세요."})

    app.include_router(system.router)
    for spec in specs:
        spec.register(app, ctx)
    return app


# uvicorn app.main:app 용. 테스트는 create_app() 을 직접 불러 메모리 시트로 띄운다.
app = create_app()
