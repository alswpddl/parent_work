"""웹 푸시 — 홈 화면에 설치한 관리자 앱으로 '울리는' 알림을 보낸다.

카카오 '나에게 보내기'는 메모용이라 알림이 울리지 않는다. 그래서 같은 내용을 휴대폰 푸시로도 보낸다.
외부 라이브러리 없이 표준만 따른다:
  - 암호화: RFC 8291 (aes128gcm, ECDH P-256 + HKDF-SHA256)
  - 서버 인증: RFC 8292 VAPID (ES256 JWT)
VAPID 키는 처음 쓸 때 만들어 시스템 시트(토큰 탭)에 넣어 둔다 → Render에 따로 넣을 값이 없다.
구독(휴대폰마다 하나)도 같은 토큰 탭에 'push:sub:…' 키로 저장한다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .http import HttpFunc, http_request

log = logging.getLogger(__name__)

VAPID_KEY = "push:vapid"
SUB_PREFIX = "push:sub:"
RECORD_SIZE = 4096


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def _raw_public(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def encrypt(payload: bytes, p256dh: str, auth: str, *, salt: bytes | None = None, server_key: ec.EllipticCurvePrivateKey | None = None) -> bytes:
    """RFC 8291 aes128gcm 본문 하나(레코드 1개)를 만든다."""
    ua_public = unb64u(p256dh)
    auth_secret = unb64u(auth)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    as_private = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public = _raw_public(as_private.public_key())
    shared = as_private.exchange(ec.ECDH(), ua_key)
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)  # \x02 = 마지막 레코드
    header = salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public)]) + as_public
    return header + body


@dataclass
class PushResult:
    sent: int = 0
    failed: int = 0
    removed: int = 0


class WebPushClient:
    def __init__(self, tokens: Any, subject: str, http: HttpFunc = http_request):
        self.tokens = tokens  # TokenRepo
        self.subject = subject if subject.startswith(("mailto:", "https://")) else "mailto:noreply@example.com"
        self.http = http
        self._key: ec.EllipticCurvePrivateKey | None = None

    # ---------------------------------------------------------------- 키
    def _private(self) -> ec.EllipticCurvePrivateKey:
        if self._key:
            return self._key
        pem = self.tokens.get_value(VAPID_KEY)
        if pem:
            key = serialization.load_pem_private_key(pem.encode(), password=None)
            assert isinstance(key, ec.EllipticCurvePrivateKey)
        else:
            key = ec.generate_private_key(ec.SECP256R1())
            pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
            self.tokens.set_many({VAPID_KEY: (pem, None)})
        self._key = key
        return key

    def public_key(self) -> str:
        """브라우저 구독에 넣는 applicationServerKey (base64url)."""
        return b64u(_raw_public(self._private().public_key()))

    # ---------------------------------------------------------------- 구독
    @staticmethod
    def _sub_key(endpoint: str) -> str:
        return SUB_PREFIX + hashlib.sha256(endpoint.encode()).hexdigest()[:20]

    def subscribe(self, endpoint: str, p256dh: str, auth: str, label: str = "") -> None:
        if not endpoint.startswith("https://"):
            raise ValueError("알림 주소가 올바르지 않아요.")
        unb64u(p256dh), unb64u(auth)  # 형식 확인
        value = json.dumps({"endpoint": endpoint, "p256dh": p256dh, "auth": auth, "label": label[:40]}, ensure_ascii=False)
        self.tokens.set_many({self._sub_key(endpoint): (value, None)})

    def unsubscribe(self, endpoint: str) -> None:
        self.tokens.delete_keys([self._sub_key(endpoint)])

    def subscriptions(self) -> list[dict]:
        out = []
        for row in self.tokens.rows(fresh=True):
            if str(row.get("key", "")).startswith(SUB_PREFIX):
                try:
                    d = json.loads(row.get("value") or "{}")
                    d["key"] = row["key"]
                    out.append(d)
                except json.JSONDecodeError:
                    continue
        return out

    def has(self, endpoint: str) -> bool:
        return any(s.get("endpoint") == endpoint for s in self.subscriptions())

    # ---------------------------------------------------------------- 보내기
    def _vapid_header(self, endpoint: str) -> str:
        u = urlsplit(endpoint)
        claims = {"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": self.subject}
        token = jwt.encode(claims, self._private(), algorithm="ES256")
        return f"vapid t={token}, k={self.public_key()}"

    def send_one(self, sub: dict, message: dict) -> int:
        body = encrypt(json.dumps(message, ensure_ascii=False).encode(), sub["p256dh"], sub["auth"])
        r = self.http(
            "POST",
            sub["endpoint"],
            headers={
                "Authorization": self._vapid_header(sub["endpoint"]),
                "Content-Encoding": "aes128gcm",
                "Content-Type": "application/octet-stream",
                "TTL": "86400",  # 휴대폰이 꺼져 있어도 하루 동안은 기다렸다 전달
                "Urgency": "high",
            },
            data=body,
            timeout=10,
        )
        return r.status

    def send_all(self, title: str, body: str, url: str = "/", tag: str = "") -> PushResult:
        res = PushResult()
        message = {"title": title, "body": body[:400], "url": url, "tag": tag or title}
        gone: list[str] = []
        for sub in self.subscriptions():
            try:
                status = self.send_one(sub, message)
            except Exception:  # noqa: BLE001 — 한 대가 실패해도 나머지는 보낸다
                log.exception("웹 푸시 실패")
                res.failed += 1
                continue
            if 200 <= status < 300:
                res.sent += 1
            elif status in (404, 410):  # 앱을 지웠거나 알림을 끈 휴대폰
                gone.append(sub["key"])
            else:
                log.warning("웹 푸시 응답 %s (%s)", status, urlsplit(sub["endpoint"]).netloc)
                res.failed += 1
        if gone:
            self.tokens.delete_keys(gone)
            res.removed = len(gone)
        return res
