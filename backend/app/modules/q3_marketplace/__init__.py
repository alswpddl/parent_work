"""3분기: 스마트스토어·쿠팡 주문 엑셀 통합 수집."""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    from .service import MarketplaceService

    ctx.services["marketplace"] = MarketplaceService(ctx)
    if hasattr(app, "routes"):
        from .router import router

        app.include_router(router)


MODULE = ModuleSpec(name="q3_marketplace", title="오픈마켓", quarter=3, register=register, requires=("q1_orders",))
