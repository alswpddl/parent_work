"""서버 오류를 개발자 휴대폰에만 푸시로 알리기 (관리자 앱 → 카톡·알림 → '서버 오류 알림 받기'를 켠 휴대폰).

같은 오류는 10분에 한 번만. 알림 보내는 동안 손님 응답이 늦어지지 않게 따로 돌린다.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

log = logging.getLogger(__name__)
_last: dict[str, float] = {}
_lock = threading.Lock()
QUIET_SEC = 600


def should_send(key: str, now: float | None = None) -> bool:
    t = time.monotonic() if now is None else now
    with _lock:
        if t - _last.get(key, -1e9) < QUIET_SEC:
            return False
        _last[key] = t
        return True


def dev_alert(ctx: Any, title: str, body: str, key: str = "", *, wait: bool = False) -> bool:
    """보낼 차례면 True. 휴대폰이 없거나 실패해도 예외를 던지지 않는다."""
    push = getattr(ctx, "push", None)
    if push is None or not should_send(key or title):
        return False

    def go() -> None:
        try:
            if any(s.get("dev") for s in push.subscriptions()):
                push.send_all(title, body, url="/settings?tab=system", tag=f"dev:{key or title}", dev_only=True)
        except Exception:  # noqa: BLE001
            log.exception("개발자 알림 실패")

    if wait:
        go()
    else:
        threading.Thread(target=go, daemon=True).start()
    return True
