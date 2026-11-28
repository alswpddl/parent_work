"""휴대폰 알림(웹 푸시): 암호화가 표준대로 풀리는지, 서명, 구독 저장, 끊긴 휴대폰 정리, 알림 창구 연결"""
from __future__ import annotations

import json

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.integrations.webpush import SUB_PREFIX, _hkdf, b64u, encrypt, unb64u


class Phone:
    """브라우저 쪽 흉내: 키를 만들고, 받은 암호문을 RFC 8291 대로 푼다."""

    def __init__(self, endpoint="https://fcm.googleapis.com/fcm/send/abc123"):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.pub = self.key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.auth = b"0123456789abcdef"
        self.endpoint = endpoint

    @property
    def keys(self):
        return {"p256dh": b64u(self.pub), "auth": b64u(self.auth)}

    def decrypt(self, body: bytes) -> dict:
        salt, rs, idlen = body[:16], int.from_bytes(body[16:20], "big"), body[20]
        as_pub = body[21 : 21 + idlen]
        assert rs == 4096 and idlen == 65
        shared = self.key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
        ikm = _hkdf(self.auth, shared, b"WebPush: info\x00" + self.pub + as_pub, 32)
        cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
        nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
        plain = AESGCM(cek).decrypt(nonce, body[21 + idlen :], None)
        assert plain.endswith(b"\x02")
        return json.loads(plain[:-1])


def test_encrypt_roundtrip():
    phone = Phone()
    body = encrypt(json.dumps({"title": "새 주문"}, ensure_ascii=False).encode(), **phone.keys)
    assert phone.decrypt(body) == {"title": "새 주문"}


def test_vapid_key_is_made_once_and_kept(full_ctx):
    p = full_ctx.push
    k1 = p.public_key()
    assert len(unb64u(k1)) == 65
    p._key = None  # 서버 재시작 흉내 → 시트에서 다시 읽어야 같은 키
    assert p.public_key() == k1


def test_subscribe_send_and_cleanup(full_ctx, http):
    p = full_ctx.push
    a, b = Phone("https://fcm.googleapis.com/fcm/send/AAA"), Phone("https://web.push.apple.com/BBB")
    p.subscribe(a.endpoint, label="아버지 폰", **a.keys)
    p.subscribe(b.endpoint, **b.keys)
    p.subscribe(b.endpoint, **b.keys)  # 같은 폰 두 번 → 하나
    assert len(p.subscriptions()) == 2

    http.queue("fcm.googleapis.com", 201, {})
    http.queue("web.push.apple.com", 410, {})  # 앱을 지운 폰
    res = p.send_all("아침 브리핑", "오늘 택배 3건", url="/today")
    assert (res.sent, res.removed) == (1, 1)
    assert [s["endpoint"] for s in p.subscriptions()] == [a.endpoint]

    call = http.by("fcm.googleapis.com")[0]
    h = call["headers"]
    assert h["Content-Encoding"] == "aes128gcm" and h["TTL"] == "86400"
    assert a.decrypt(call["data"]) == {"title": "아침 브리핑", "body": "오늘 택배 3건", "url": "/today", "tag": "아침 브리핑"}
    # VAPID 서명: 우리 공개키로 검증되고, aud 는 푸시 서버 주소
    t = h["Authorization"].split("t=")[1].split(",")[0]
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), unb64u(p.public_key()))
    claims = jwt.decode(t, pub, algorithms=["ES256"], audience="https://fcm.googleapis.com")
    assert claims["sub"] == "https://app.example.com"


def test_bad_endpoint_rejected(full_ctx):
    with pytest.raises(ValueError):
        full_ctx.push.subscribe("http://evil.example/x", **Phone().keys)


def test_owner_notifier_sends_push_too(full_ctx, http):
    phone = Phone()
    full_ctx.push.subscribe(phone.endpoint, **phone.keys)
    http.queue("fcm.googleapis.com", 201, {})
    assert full_ctx.notifier.send("아침브리핑", "🌅 오늘 할 일\n택배 2건", path="/") is True
    msg = phone.decrypt(http.by("fcm.googleapis.com")[0]["data"])
    assert msg["title"] == "아침 브리핑" and msg["body"].startswith("오늘 할 일")  # 그림 문자는 뺌
    channels = [m["channel"] for m in full_ctx.messages.recent(10)]
    assert "앱 알림" in channels and "카카오(나에게)" in channels


def test_push_failure_does_not_break(full_ctx, http, monkeypatch):
    monkeypatch.setattr(full_ctx.push, "subscriptions", lambda: (_ for _ in ()).throw(RuntimeError("시트 오류")))
    assert full_ctx.notifier.send("재고경고", "멸치 부족") is True  # 카카오는 갔음


def test_subscriptions_live_in_token_tab(full_ctx):
    phone = Phone()
    full_ctx.push.subscribe(phone.endpoint, **phone.keys)
    full_ctx.push.public_key()  # 처음 쓸 때 만들어져 저장
    keys = [r["key"] for r in full_ctx.tokens.rows(fresh=True)]
    assert any(k.startswith(SUB_PREFIX) for k in keys) and "push:vapid" in keys


def test_dev_only_alerts_go_to_dev_phones(full_ctx, http):
    from app.services import dev_alert as da

    da._last.clear()
    parent, me = Phone("https://fcm.googleapis.com/fcm/send/PARENT"), Phone("https://fcm.googleapis.com/fcm/send/MINJE")
    p = full_ctx.push
    p.subscribe(parent.endpoint, label="아버지 폰", **parent.keys)
    p.subscribe(me.endpoint, label="민제 폰", **me.keys)
    assert p.set_dev(me.endpoint, True) and not p.set_dev("https://nope.example/x", True)
    p.subscribe(me.endpoint, **me.keys)  # 다시 구독해도 개발자 설정 유지
    assert [s["label"] for s in p.subscriptions() if s.get("dev")] == ["민제 폰"]

    http.queue("MINJE", 201, {})
    assert da.dev_alert(full_ctx, "서버 오류", "GET /api/x\nKeyError", key="k1", wait=True)
    sent = http.by("fcm.googleapis.com")
    assert len(sent) == 1 and "MINJE" in sent[0]["url"]
    assert me.decrypt(sent[0]["data"])["title"] == "서버 오류"
    # 같은 오류는 10분에 한 번
    assert not da.dev_alert(full_ctx, "서버 오류", "또", key="k1", wait=True)
    # 일반 알림(아침 브리핑)은 두 폰 모두
    http.queue("PARENT", 201, {})
    http.queue("MINJE", 201, {})
    assert p.send_all("아침 브리핑", "택배 1건").sent == 2
