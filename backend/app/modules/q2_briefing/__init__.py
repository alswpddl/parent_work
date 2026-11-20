"""2분기: 매일 아침 부모님 카톡 브리핑 + 카카오 연결 관리."""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    from .report import BriefingService, core_section

    svc = BriefingService(ctx)
    ctx.services["briefing"] = svc
    ctx.briefing.register("생산·출고", core_section, order=10)
    ctx.jobs.register(
        "morning_briefing", lambda c: svc.send(), cron="0 8 * * *",
        description="아침 브리핑 카톡 발송", module="q2_briefing",
    )
    ctx.jobs.register(
        "kakao_token_refresh", lambda c: c.kakao.refresh() if c.kakao.configured else {"skipped": "키 없음"},
        cron="0 4 * * 1", description="카카오 토큰 갱신 (주 1회)", module="q2_briefing",
    )
    if hasattr(app, "routes"):
        from .router import router

        app.include_router(router)


MODULE = ModuleSpec(name="q2_briefing", title="아침 브리핑", quarter=2, register=register, requires=("q1_orders",))
