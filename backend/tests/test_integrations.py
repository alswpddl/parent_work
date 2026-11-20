from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta

import pytest

from app.core.signing import sign, verify
from app.core.timeutil import now
from app.integrations.kakao import KakaoError, split_text
from app.integrations.solapi import SolapiClient, SolapiError


# ---------------------------------------------------------------- 카카오
def test_split_text_keeps_lines():
    text = "\n".join(f"{i}번째 줄 " + "가" * 30 for i in range(20))
    chunks = split_text(text, 200)
    assert all(len(c) <= 200 for c in chunks)
    assert "\n".join(chunks).replace("\n", "") == text.replace("\n", "")
    assert split_text("짧은 글") == ["짧은 글"]
    assert all(len(c) <= 200 for c in split_text("가" * 450))


def test_kakao_send_uses_text_template(full_ctx, http):
    n = full_ctx.kakao.send_text("안녕하세요", link_url="https://app.example.com/", button_title="열기")
    assert n == 1
    call = http.by("talk/memo/default/send")[0]
    assert call["headers"]["Authorization"] == "Bearer acc-1"
    tpl = json.loads(call["form"]["template_object"])
    assert tpl["object_type"] == "text" and tpl["text"] == "안녕하세요"
    assert tpl["link"]["web_url"] == "https://app.example.com/" and tpl["button_title"] == "열기"


def test_kakao_long_message_is_split(full_ctx, http):
    text = "\n".join("· 참기름 1.8L 10개 (3건) 내일 납기" for _ in range(20))
    n = full_ctx.kakao.send_text(text, link_url="https://app.example.com/")
    assert n >= 3 and len(http.by("memo/default/send")) == n


def test_kakao_refreshes_expired_access_token(full_ctx, http):
    full_ctx.tokens.set_many({"kakao_access_token": ("old", now() - timedelta(minutes=1))})
    full_ctx.kakao.send_text("x", link_url="https://app.example.com/")
    token_call = http.by("oauth/token")[0]
    assert token_call["form"]["grant_type"] == "refresh_token" and token_call["form"]["refresh_token"] == "ref-1"
    assert http.by("memo/default/send")[0]["headers"]["Authorization"] == "Bearer acc-new"
    # 갱신 응답에 refresh_token 이 없으면 기존 것을 그대로 둔다
    assert full_ctx.tokens.get_value("kakao_refresh_token") == "ref-1"


def test_kakao_retries_once_on_401(full_ctx, http):
    http.queue("memo/default/send", 401, {"code": -401, "msg": "this access token is already expired"})
    full_ctx.kakao.send_text("x", link_url="https://app.example.com/")
    assert len(http.by("oauth/token")) == 1 and len(http.by("memo/default/send")) == 2


def test_kakao_missing_scope_needs_reconnect(full_ctx, http):
    http.queue("memo/default/send", 403, {"code": -402, "msg": "insufficient scopes."})
    with pytest.raises(KakaoError) as e:
        full_ctx.kakao.send_text("x", link_url="https://app.example.com/")
    assert e.value.need_reconnect


def test_kakao_connect_flow(full_ctx, http):
    full_ctx.kakao.disconnect()
    assert full_ctx.kakao.status()["connected"] is False
    url = full_ctx.kakao.authorize_url("STATE")
    assert url.startswith("https://kauth.kakao.com/oauth/authorize?") and "scope=talk_message" in url
    assert "redirect_uri=https%3A%2F%2Fapi.example.com%2Fapi%2Fintegrations%2Fkakao%2Fcallback" in url
    http.queue("oauth/token", 200, {"access_token": "A", "expires_in": 21599, "refresh_token": "R", "refresh_token_expires_in": 5184000})
    info = full_ctx.kakao.exchange_code("CODE")
    assert info["nickname"] == "엄마"
    st = full_ctx.kakao.status()
    assert st["connected"] and st["nickname"] == "엄마"
    assert http.by("oauth/token")[-1]["form"]["grant_type"] == "authorization_code"


def test_notifier_logs_results(full_ctx, http):
    assert full_ctx.notifier.send("테스트", "hello")
    http.queue("memo/default/send", 400, {"code": -2, "msg": "bad"})
    assert not full_ctx.notifier.send("테스트", "hello")
    results = [m["result"] for m in full_ctx.messages.recent(10)]
    assert "성공" in results and "실패" in results


def test_signing_roundtrip():
    tok = sign("k" * 32, "stmt:S-1", 60)
    assert verify("k" * 32, tok) == "stmt:S-1"
    assert verify("x" * 32, tok) is None
    assert verify("k" * 32, sign("k" * 32, "a", -1)) is None
    assert verify("k" * 32, "garbage") is None


# ---------------------------------------------------------------- 솔라피
def test_solapi_signature_and_payload(http):
    c = SolapiClient(api_key="KEY", api_secret="SECRET", sender="031-000-0000", pfid="PF", http=http)
    h = c.auth_header(date="2026-11-19T00:00:00Z", salt="abc")
    expect = hmac.new(b"SECRET", b"2026-11-19T00:00:00Zabc", hashlib.sha256).hexdigest()
    assert h == f"HMAC-SHA256 apiKey=KEY, date=2026-11-19T00:00:00Z, salt=abc, signature={expect}"

    c.send_alimtalk(to="010-1234-5678", template_id="T1", variables={"거래처명": "한솥", "#{송장번호}": "123"})
    body = http.by("solapi")[0]["json"]["messages"][0]
    assert body["to"] == "01012345678" and body["from"] == "0310000000"
    ko = body["kakaoOptions"]
    assert ko["pfId"] == "PF" and ko["templateId"] == "T1" and ko["disableSms"] is False
    assert ko["variables"] == {"#{거래처명}": "한솥", "#{송장번호}": "123"}


def test_solapi_errors(http):
    c = SolapiClient(api_key="K", api_secret="S", sender="", pfid="PF", http=http)
    with pytest.raises(SolapiError):
        c.send_alimtalk(to="02-123-4567", template_id="T", variables={})  # 휴대폰 아님
    http.queue("solapi", 200, {"failedMessageList": [{"statusMessage": "템플릿 불일치"}]})
    with pytest.raises(SolapiError, match="템플릿 불일치"):
        c.send_alimtalk(to="01012345678", template_id="T", variables={})
    assert c.build_alimtalk(to="01012345678", template_id="T", variables={})["kakaoOptions"]["disableSms"] is True
