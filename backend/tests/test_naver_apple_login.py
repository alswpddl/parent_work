"""손님 네이버 · 애플 로그인"""
import base64
import json

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.errors import UnauthorizedError, ValidationFailed
from app.modules.q2_web_order.extras import KakaoCompleteIn
from tests.test_web_order import _svc


def test_naver_login(full_ctx, http):
    s = _svc(full_ctx)
    assert not s.info().naver_login
    with pytest.raises(ValidationFailed, match="네이버"):
        s.naver_start_url()
    full_ctx.config.naver_client_id, full_ctx.config.naver_client_secret = "nid", "nsecret"
    assert s.info().naver_login
    url = s.naver_start_url()
    assert url.startswith("https://nid.naver.com/oauth2.0/authorize?") and "auth%2Fnaver%2Fcallback" in url
    state = url.split("state=")[1].split("&")[0]
    with pytest.raises(UnauthorizedError):
        s.naver_callback("c", "forged")
    http.queue("nid.naver.com/oauth2.0/token", 200, {"access_token": "n-acc"})
    http.queue("openapi.naver.com/v1/nid/me", 200, {"resultcode": "00", "response": {"id": "n-1", "name": "최민제"}})
    r = s.naver_callback("code1", state)
    assert r.ticket and r.nickname == "최민제"
    auth = s.kakao_complete(KakaoCompleteIn(ticket=r.ticket, name="최민제", phone="010-5151-2323", agree_privacy=True))
    assert full_ctx.customers.get(s.member(auth.token).customer_id, fresh=True)["naver_id"] == "n-1"
    http.queue("nid.naver.com/oauth2.0/token", 200, {"access_token": "n-acc2"})
    http.queue("openapi.naver.com/v1/nid/me", 200, {"response": {"id": "n-1"}})
    assert s.naver_callback("code2", state).token


def _id_token(claims: dict) -> str:
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b({'alg': 'RS256'})}.{b(claims)}.sig"


def test_apple_login(full_ctx, http):
    s = _svc(full_ctx)
    assert not s.info().apple_login
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    cfg = full_ctx.config
    cfg.apple_client_id, cfg.apple_team_id, cfg.apple_key_id = "kr.gayeom.login", "TEAM123456", "KEY1234567"
    cfg.apple_private_key = pem.replace("\n", "\\n")  # Render 에 한 줄로 넣어도 됨
    assert s.info().apple_login
    url = s.apple_start_url()
    assert "response_mode=form_post" in url and "auth%2Fapple%2Fcallback" in url
    state = url.split("state=")[1].split("&")[0]

    http.queue("appleid.apple.com/auth/token", 200, {"id_token": _id_token({"aud": "kr.gayeom.login", "sub": "a-1"})})
    r = s.apple_callback("code1", state, json.dumps({"name": {"firstName": "민제", "lastName": "최"}}))
    assert r.ticket and r.nickname == "최민제"
    sent = http.by("appleid.apple.com/auth/token")[0]["form"]
    claims = jwt.decode(sent["client_secret"], key.public_key(), algorithms=["ES256"], audience="https://appleid.apple.com")
    assert claims["iss"] == "TEAM123456" and claims["sub"] == "kr.gayeom.login"
    assert jwt.get_unverified_header(sent["client_secret"])["kid"] == "KEY1234567"

    auth = s.kakao_complete(KakaoCompleteIn(ticket=r.ticket, name="최민제", phone="010-6161-2424", agree_privacy=True))
    assert full_ctx.customers.get(s.member(auth.token).customer_id, fresh=True)["apple_id"] == "a-1"
    http.queue("appleid.apple.com/auth/token", 200, {"id_token": _id_token({"aud": "kr.gayeom.login", "sub": "a-1"})})
    assert s.apple_callback("code2", state).token
    # 다른 앱용 토큰은 거절
    http.queue("appleid.apple.com/auth/token", 200, {"id_token": _id_token({"aud": "other", "sub": "a-1"})})
    with pytest.raises(ValidationFailed):
        s.apple_callback("code3", state)
