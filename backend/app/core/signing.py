"""만료 시각이 있는 서명 문자열.

- 거래명세표 PDF 공개 링크 (로그인 없이 거래처가 열어볼 수 있게)
- 카카오 로그인 state (CSRF 방지)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(secret: str, payload: str, ttl_sec: int) -> str:
    exp = int(time.time()) + ttl_sec
    body = f"{payload}|{exp}"
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()[:18]
    return f"{_b64(body.encode())}.{_b64(sig)}"


def verify(secret: str, token: str) -> str | None:
    """정상이면 payload, 위조·만료면 None."""
    try:
        body_b64, sig_b64 = token.split(".", 1)
        body = _unb64(body_b64).decode()
        expect = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()[:18]
        if not hmac.compare_digest(expect, _unb64(sig_b64)):
            return None
        payload, exp = body.rsplit("|", 1)
        if int(exp) < time.time():
            return None
        return payload
    except (ValueError, UnicodeDecodeError):
        return None
