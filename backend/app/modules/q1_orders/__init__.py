"""1분기: 카톡 주문 AI 파서 + 주문 저장/조회/수정 + 생산 집계."""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    if hasattr(app, "routes"):  # FastAPI 가 있을 때만 라우터 등록 (테스트·스크립트에서는 건너뜀)
        from .router import router

        app.include_router(router)


MODULE = ModuleSpec(name="q1_orders", title="주문 넣기", quarter=1, register=register, requires=("q1_masters",))
