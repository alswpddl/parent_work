from __future__ import annotations

import logging

from ..core.repository import Repository
from ..core.sheet_schema import LOGS
from ..core.timeutil import now

log = logging.getLogger(__name__)


class LogRepo(Repository[dict]):
    spec = LOGS

    def write(self, action: str, target: str, detail: str = "", *, actor: str = "관리자", result: str = "성공") -> None:
        """_기록 탭에 한 줄 남긴다. 기록 실패가 본 작업을 막지 않도록 예외를 삼킨다."""
        try:
            self.insert(
                {"ts": now(), "actor": actor, "action": action, "target": target, "detail": detail[:500], "result": result}
            )
        except Exception:  # noqa: BLE001
            log.exception("_기록 쓰기 실패: %s %s", action, target)
