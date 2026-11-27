"""4분기: 원부자재(용기·박스·라벨) 자동 차감, 안전재고 경고, 소진 예측 + 숙성 저장소 지도."""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    from .service import InventoryService

    svc = InventoryService(ctx)
    ctx.services["inventory"] = svc
    ctx.bus.subscribe("order.shipped", svc.on_shipped)
    ctx.bus.subscribe("order.unshipped", svc.on_unshipped)
    ctx.bus.subscribe("order.cancelled", svc.on_cancelled)
    ctx.briefing.register("재고", svc.briefing_section, order=20)

    from .aging import AgingService

    aging = AgingService(ctx)
    ctx.services["aging"] = aging

    def aging_section(c, day):
        from ...core.briefing import BriefingSection

        lines = aging.briefing_lines()
        return BriefingSection(title="숙성 저장소", lines=lines, priority=25) if lines else None

    ctx.briefing.register("숙성 저장소", aging_section, order=25)
    ctx.jobs.register(
        "stock_check", lambda c: svc.check_and_alert(), cron="30 7 * * *",
        description="안전재고 점검·카톡 경고", module="q4_inventory",
    )
    if hasattr(app, "routes"):
        from .router import router, tanks_router

        app.include_router(tanks_router)  # /api/inventory/tanks… 를 '/{item_id}' 보다 먼저
        app.include_router(router)


MODULE = ModuleSpec(name="q4_inventory", title="자재 재고", quarter=4, register=register, requires=("q1_shipping",))
