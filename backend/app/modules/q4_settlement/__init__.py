"""4분기: 월말 정산 · 거래명세표 PDF · 발송 · 수금 관리."""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    from .service import SettlementService

    svc = SettlementService(ctx)
    ctx.services["settlement"] = svc
    ctx.briefing.register("미수금", svc.briefing_section, order=40)
    ctx.jobs.register(
        "monthly_settlement", lambda c: svc.monthly_job(), cron="0 9 1 * *",
        description="지난달 거래명세표 생성·카톡 안내", module="q4_settlement",
    )
    if hasattr(app, "routes"):
        from .router import public_router, router

        app.include_router(router)
        app.include_router(public_router)


MODULE = ModuleSpec(name="q4_settlement", title="월말 정산", quarter=4, register=register, requires=("q1_shipping",))
