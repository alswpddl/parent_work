"""3분기: 택배 운송장 엑셀 역등록 + 화물 차량정보 입력."""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    from .service import TrackingService

    ctx.services["tracking"] = TrackingService(ctx)
    if hasattr(app, "routes"):
        from .router import router

        app.include_router(router)


MODULE = ModuleSpec(name="q3_tracking", title="송장 등록", quarter=3, register=register, requires=("q1_shipping",))
