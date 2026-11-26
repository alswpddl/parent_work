"""사람이 읽기 쉬운 ID 발급."""

from __future__ import annotations

import re
import secrets
from datetime import date
from typing import Iterable


# 헷갈리는 글자(0·O, 1·I·L)를 뺀 32자
ORDER_CODE_CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
# 새 형식 20261126-K7Q3 + 예전 형식 O-20261126-003 (예전 주문도 계속 찾을 수 있게)
ORDER_ID_PATTERN = r"(?:O-\d{8}-\d{3}|\d{8}-[2-9A-HJKMNP-Z]{4})"


def next_order_id(existing_ids: Iterable[str], day: date) -> str:
    """20261126-K7Q3 형식: 날짜 + 무작위 4글자 (하루 주문 수가 드러나지 않고 남의 번호를 짐작하기 어렵다)."""
    taken = set(existing_ids)
    while True:
        oid = f"{day:%Y%m%d}-" + "".join(secrets.choice(ORDER_CODE_CHARS) for _ in range(4))
        if oid not in taken:
            return oid


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
