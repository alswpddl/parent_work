"""4분기: 단골 거래처 발주 주기 리마인드."""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    from .service import ReorderService

    svc = ReorderService(ctx)
    ctx.services["reorder"] = svc
    ctx.briefing.register("리마인드", svc.briefing_section, order=30)
    ctx.jobs.register(
        "reorder_scan", lambda c: svc.job(), cron="40 7 * * *",
        description="거래처 주문 주기 계산·거래처 탭 갱신", module="q4_reorder",
    )
    if hasattr(app, "routes"):
        from .router import router

        app.include_router(router)


MODULE = ModuleSpec(name="q4_reorder", title="리마인드", quarter=4, register=register, requires=("q1_orders",))
