"""2분기: 거래처 모바일 셀프 주문 (/order/:token)."""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    from .service import SelfOrderService

    svc = SelfOrderService(ctx)
    ctx.services["self_order"] = svc
    ctx.bus.subscribe("order.created", svc.on_order_created)

    if hasattr(app, "routes"):  # FastAPI 가 있을 때만 라우터 등록
        from .router import admin_router, public_router

        app.include_router(admin_router)
        app.include_router(public_router)


MODULE = ModuleSpec(name="q2_self_order", title="셀프 주문", quarter=2, register=register, requires=("q1_orders",))
