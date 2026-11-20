"""3분기: 거래처 출고 알림톡 (솔라피)."""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    from .service import NotifyService

    svc = NotifyService(ctx)
    ctx.services["notify"] = svc
    ctx.bus.subscribe("order.shipped", svc.on_shipped)
    ctx.bus.subscribe("order.shipping_info", svc.on_shipped)
    ctx.bus.subscribe("order.created", svc.on_created)
    if hasattr(app, "routes"):
        from .router import router

        app.include_router(router)


MODULE = ModuleSpec(name="q3_notify", title="알림톡", quarter=3, register=register, requires=("q1_shipping",))
