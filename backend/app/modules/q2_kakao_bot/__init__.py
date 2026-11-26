"""카카오톡 채널 챗봇 (카카오 챗봇 관리자센터 '스킬' 서버).

손님이 공장 카카오톡 채널에 말을 걸면 → 카카오가 POST /api/kakao/skill?key=… 로 보냄 → 5초 안에 답.
정해진 질문(상품·가격, 택배비, 받는 날, 계좌, 주문 조회, 전화, 주문하기)에만 정해진 답을 한다. AI 는 쓰지 않는다.
KAKAO_SKILL_KEY 환경변수가 비어 있으면 꺼져 있다.
"""

from __future__ import annotations

from .. import ModuleSpec


def register(app, ctx) -> None:
    from .service import KakaoBot

    ctx.services["kakao_bot"] = KakaoBot(ctx)
    if hasattr(app, "routes"):
        from .router import router

        app.include_router(router)


MODULE = ModuleSpec(name="q2_kakao_bot", title="카카오톡 챗봇", quarter=2, register=register, requires=("q2_web_order",))
