"""분기별 기능 모듈 레지스트리.

새 모듈 추가 방법
1) app/modules/<이름>/__init__.py 에 MODULE = ModuleSpec(...) 정의
2) register(app, ctx) 안에서 라우터 등록 / ctx.bus.subscribe(...) / ctx.jobs.register(...) / ctx.briefing.register(...)
3) KNOWN_MODULES 에 이름 추가, 환경변수 ENABLED_MODULES 에 이름 추가
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModuleSpec:
    name: str
    title: str  # 화면 탭 이름
    quarter: int
    register: Callable[[Any, Any], None]  # (FastAPI app, AppContext)
    requires: tuple[str, ...] = ()


# 등록 순서 = 로드 순서 (의존 모듈이 먼저 오도록)
KNOWN_MODULES: list[str] = [
    "q1_masters",
    "q1_orders",
    "q1_shipping",
    "q2_self_order",
    "q2_briefing",
    "q3_tracking",
    "q3_notify",
    "q3_marketplace",
    "q4_inventory",
    "q4_settlement",
    "q4_reorder",
]


def load_modules(names: list[str]) -> list[ModuleSpec]:
    wanted = set(names)
    loaded: list[ModuleSpec] = []
    loaded_names: set[str] = set()
    for name in KNOWN_MODULES:
        if name not in wanted:
            continue
        mod = importlib.import_module(f"app.modules.{name}")
        spec: ModuleSpec = getattr(mod, "MODULE")
        missing = [r for r in spec.requires if r not in loaded_names]
        if missing:
            log.error("모듈 %s 은(는) %s 가 필요해서 건너뜀", name, missing)
            continue
        loaded.append(spec)
        loaded_names.add(name)
    unknown = wanted - set(KNOWN_MODULES)
    if unknown:
        log.warning("알 수 없는 모듈 이름: %s", sorted(unknown))
    return loaded


def register_without_app(specs: list[ModuleSpec], ctx: Any) -> None:
    """FastAPI 없이 모듈의 이벤트·작업·브리핑만 등록 (테스트·스크립트용)."""

    class _NoApp:
        def include_router(self, *a, **k):
            return None

    for s in specs:
        s.register(_NoApp(), ctx)
