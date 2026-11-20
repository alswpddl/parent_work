"""시스템 시트: 외부 서비스 토큰 저장소와 발송 기록."""

from __future__ import annotations

import logging
from datetime import datetime

from ..core.repository import Repository
from ..core.sheet_schema import SYS_MESSAGES, SYS_TOKENS, TabSpec
from ..core.sheets import SheetsClient
from ..core.timeutil import now

log = logging.getLogger(__name__)


class TokenRepo(Repository[dict]):
    spec = SYS_TOKENS

    def __init__(self, sheets: SheetsClient, spec: TabSpec | None = None):
        super().__init__(sheets, spec)

    def get_value(self, key: str) -> str:
        d = self.get(key, fresh=True)
        return (d or {}).get("value") or ""

    def get_entry(self, key: str) -> tuple[str, datetime | None]:
        d = self.get(key, fresh=True) or {}
        return d.get("value") or "", d.get("expires_at")

    def set_many(self, values: dict[str, tuple[str, datetime | None]]) -> None:
        existing = {d.get("key") for d in self.rows(fresh=True)}
        ts = now()
        updates = []
        inserts = []
        for k, (v, exp) in values.items():
            row = {"value": v, "expires_at": exp, "updated_at": ts}
            if k in existing:
                updates.append(((k,), row))
            else:
                inserts.append({"key": k, **row})
        self.update_many(updates)
        self.insert_many(inserts)

    def delete_keys(self, keys: list[str]) -> None:
        self.delete_many([(k,) for k in keys])


class MessageLogRepo(Repository[dict]):
    spec = SYS_MESSAGES

    def __init__(self, sheets: SheetsClient, spec: TabSpec | None = None):
        super().__init__(sheets, spec)

    def write(
        self,
        *,
        channel: str,
        kind: str,
        to: str,
        result: str,
        content: str = "",
        order_id: str = "",
        error: str = "",
    ) -> None:
        try:
            self.insert(
                {
                    "ts": now(), "channel": channel, "kind": kind, "to": to, "order_id": order_id,
                    "result": result, "content": content[:300], "error": error[:300],
                }
            )
        except Exception:  # noqa: BLE001 — 기록 실패가 발송을 막지 않게
            log.exception("발송기록 쓰기 실패")

    def recent(self, limit: int = 100, order_id: str | None = None) -> list[dict]:
        rows = self.rows()
        if order_id:
            rows = [r for r in rows if r.get("order_id") == order_id]
        rows = [r for _, r in sorted(enumerate(rows), key=lambda x: (x[1].get("ts") or now(), x[0]), reverse=True)]
        return rows[:limit]
