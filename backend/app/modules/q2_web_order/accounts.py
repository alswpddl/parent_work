"""웹 주문서 손님 계정 — 휴대폰 번호 + 비밀번호.

- 비밀번호는 PBKDF2-SHA256(20만 번)으로 바꿔 거래처 탭 '웹로그인(암호화)' 칸에 저장. 원래 비밀번호는 어디에도 남지 않는다.
- 로그인하면 90일짜리 서명 토큰을 준다. 비밀번호를 바꾸면 예전 토큰은 바로 막힌다(토큰에 해시 끝자리를 넣음).
- 부모님이 시트에서 그 칸을 지우면 비밀번호 초기화 → 손님은 다시 가입하면 된다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from ...core.signing import sign, verify

ITERATIONS = 200_000
TOKEN_TTL = 90 * 24 * 3600


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(it))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


def _ver(stored: str) -> str:
    return hashlib.sha256(stored.encode()).hexdigest()[:10]


def issue_token(secret: str, customer_id: str, stored_hash: str) -> str:
    return sign(secret, f"shop:{customer_id}:{_ver(stored_hash)}", TOKEN_TTL)


def read_token(secret: str, token: str) -> tuple[str, str] | None:
    """(거래처ID, 비밀번호 버전) 또는 None"""
    payload = verify(secret, token or "")
    if not payload or not payload.startswith("shop:"):
        return None
    try:
        _, cid, ver = payload.split(":", 2)
    except ValueError:
        return None
    return cid, ver


def token_matches(ver: str, stored_hash: str) -> bool:
    return bool(stored_hash) and hmac.compare_digest(ver, _ver(stored_hash))
