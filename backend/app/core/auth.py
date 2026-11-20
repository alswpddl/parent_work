"""인증 유틸 (FastAPI 비의존).

- 관리자: PIN 입력 → 서명된 토큰(JWT, HS256) 발급. 프론트는 localStorage 에 두고 Authorization: Bearer 로 보낸다.
  (Vercel ↔ Render 는 서로 다른 사이트라 쿠키는 브라우저가 막을 수 있어 헤더 방식을 쓴다.)
- 정기작업: X-Job-Secret 헤더를 상수시간 비교.
- 로그인 시도 제한: IP 당 10분에 5회.
"""

from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

import jwt

from .errors import TooManyRequests, UnauthorizedError
from .timeutil import now

ALGO = "HS256"


def issue_admin_token(secret: str, ttl_hours: int) -> tuple[str, datetime]:
    exp = now() + timedelta(hours=ttl_hours)
    token = jwt.encode({"sub": "admin", "role": "admin", "exp": int(exp.timestamp())}, secret, algorithm=ALGO)
    return token, exp


def verify_admin_token(secret: str, token: str) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGO])
    except jwt.ExpiredSignatureError as e:
        raise UnauthorizedError("로그인이 만료됐어요. 비밀번호를 다시 넣어 주세요.") from e
    except jwt.PyJWTError as e:
        raise UnauthorizedError() from e
    if payload.get("role") != "admin":
        raise UnauthorizedError()
    return payload


def check_pin(expected: str, given: str) -> bool:
    if not expected:
        return False
    return hmac.compare_digest(expected.encode(), (given or "").encode())


def check_job_secret(expected: str, given: str | None) -> bool:
    if not expected or not given:
        return False
    return hmac.compare_digest(expected.encode(), given.encode())


class LoginLimiter:
    def __init__(self, max_attempts: int = 5, window_sec: int = 600):
        self.max_attempts = max_attempts
        self.window = window_sec
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        t = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and t - q[0] > self.window:
                q.popleft()
            if len(q) >= self.max_attempts:
                raise TooManyRequests("비밀번호를 여러 번 틀렸어요. 10분 뒤에 다시 해 주세요.")

    def fail(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)
