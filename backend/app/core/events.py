"""모듈 간 연결용 이벤트 버스.

1분기 코드는 이벤트를 '발행'만 하고, 3·4분기 모듈이 '구독'해서 기능을 덧붙인다.
→ 새 분기 기능을 붙일 때 기존 코드를 고치지 않는다.

이벤트 목록 (payload 는 dict)
- order.created     {"order": OrderOut}
- order.updated     {"order": OrderOut}
- order.shipped     {"order": OrderOut}    → Q3 알림톡, Q4 자재 차감
- order.unshipped   {"order": OrderOut}    → Q4 자재 복원
- order.cancelled   {"order": OrderOut, "was_shipped": bool}
- tracking.imported {"order_ids": [...]}  (Q3)

구독자 오류는 기록만 하고 삼킨다. 알림톡이 실패해도 출고 처리 자체는 성공해야 하기 때문.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], None]


@dataclass
class HandlerFailure:
    event: str
    handler: str
    error: str


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> None:
        self._handlers[event].append(handler)

    def handlers(self, event: str) -> list[Handler]:
        return list(self._handlers.get(event, []))

    def publish(self, event: str, payload: dict[str, Any]) -> list[HandlerFailure]:
        failures: list[HandlerFailure] = []
        for h in self.handlers(event):
            name = getattr(h, "__qualname__", repr(h))
            try:
                h(payload)
            except Exception as e:  # noqa: BLE001 — 구독자 오류는 격리
                log.exception("이벤트 %s 처리 중 오류 (%s)", event, name)
                failures.append(HandlerFailure(event, name, str(e)))
        return failures
