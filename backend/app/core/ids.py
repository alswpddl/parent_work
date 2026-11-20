"""사람이 읽기 쉬운 ID 발급."""

from __future__ import annotations

import re
import secrets
from datetime import date
from typing import Iterable


def next_order_id(existing_ids: Iterable[str], day: date) -> str:
    """O-20261118-001 형식. 같은 날 주문 중 가장 큰 번호 + 1."""
    prefix = f"O-{day:%Y%m%d}-"
    mx = 0
    for oid in existing_ids:
        if oid and oid.startswith(prefix):
            tail = oid[len(prefix):]
            if tail.isdigit():
                mx = max(mx, int(tail))
    return f"{prefix}{mx + 1:03d}"


def next_seq_id(existing_ids: Iterable[str], prefix: str, width: int = 4) -> str:
    """C0001, P0001 형식."""
    pat = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    mx = 0
    for x in existing_ids:
        m = pat.match(x or "")
        if m:
            mx = max(mx, int(m.group(1)))
    return f"{prefix}{mx + 1:0{width}d}"


def random_token(nbytes: int = 18) -> str:
    """거래처 주문 링크용 (2분기)."""
    return secrets.token_urlsafe(nbytes)
