"""1분기: 기준정보(설정·거래처·품목) 관리."""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    if hasattr(app, "routes"):  # FastAPI 가 있을 때만 라우터 등록 (테스트·스크립트에서는 건너뜀)
        from .router import router

        app.include_router(router)


MODULE = ModuleSpec(name="q1_masters", title="기본 정보", quarter=1, register=register)
