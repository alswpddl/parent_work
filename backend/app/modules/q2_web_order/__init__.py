"""웹 주문서 (/shop) — 누구나 링크로 들어와 주문하는 고객용 주문 사이트.

거래처 전용 링크(/order/:token)는 등록된 단골용이고, 이 모듈은 처음 오는 개인 고객·거래처까지 받는다.
주문이 들어오면 고객 정보는 거래처 탭에, 주문은 주문장 탭에 쌓이고 경로는 '웹주문서'.
"""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    from .service import WebOrderService

    ctx.services["web_order"] = WebOrderService(ctx)
    if hasattr(app, "routes"):
        from .router import router

        app.include_router(router)


MODULE = ModuleSpec(name="q2_web_order", title="웹 주문서", quarter=2, register=register, requires=("q1_orders",))
