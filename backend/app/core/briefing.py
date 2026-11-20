"""아침 브리핑 섹션 레지스트리.

각 분기 모듈이 '브리핑에 넣을 내용'을 함수로 등록하면 q2_briefing 이 순서대로 모아 카톡으로 보낸다.
예) q4_inventory → "⚠️ 재고 부족: 1.8L 용기 120개 (안전재고 300)"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

log = logging.getLogger(__name__)

SectionFunc = Callable[[Any, date], "BriefingSection | None"]


@dataclass
class BriefingSection:
    title: str
    lines: list[str]
    priority: int = 50  # 작을수록 위


@dataclass
class _Provider:
    name: str
    func: SectionFunc
    order: int


class BriefingRegistry:
    def __init__(self) -> None:
        self._providers: list[_Provider] = []

    def register(self, name: str, func: SectionFunc, order: int = 50) -> None:
        self._providers.append(_Provider(name, func, order))
        self._providers.sort(key=lambda p: p.order)

    def collect(self, ctx: Any, day: date) -> list[BriefingSection]:
        out: list[BriefingSection] = []
        for p in self._providers:
            try:
                sec = p.func(ctx, day)
            except Exception:  # noqa: BLE001 — 한 섹션 오류가 브리핑 전체를 막지 않게
                log.exception("브리핑 섹션 %s 오류", p.name)
                sec = BriefingSection(title=f"{p.name} 확인 실패", lines=["(잠시 뒤 다시 확인해 주세요)"], priority=99)
            if sec and sec.lines:
                out.append(sec)
        return out
