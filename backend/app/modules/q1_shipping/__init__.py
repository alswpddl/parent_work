"""1분기: 출고판(택배/화물 분기), 택배 엑셀, 화물 배차 문자, 출고 처리."""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    if hasattr(app, "routes"):  # FastAPI 가 있을 때만 라우터 등록 (테스트·스크립트에서는 건너뜀)
        from .router import router

        app.include_router(router)


MODULE = ModuleSpec(name="q1_shipping", title="출고하기", quarter=1, register=register, requires=("q1_orders",))
