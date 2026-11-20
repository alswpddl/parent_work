"""카카오톡 '나에게 보내기' — 부모님 카톡으로 브리핑·경고를 보낸다.

흐름
1) 부모님이 화면의 [카카오 연결] 버튼 → authorize_url() 로 이동 → 동의
2) 카카오가 /api/integrations/kakao/callback?code=... 로 돌려보냄 → exchange_code()
3) 토큰은 시스템 시트 '토큰' 탭에 저장. 보낼 때마다 만료 10분 전이면 자동 갱신
4) 리프레시 토큰은 남은 기간이 1개월 미만일 때만 새로 내려오므로, 주 1회 refresh 작업으로 계속 이어 간다

텍스트 템플릿은 글자 수 200자 제한이 있어 긴 브리핑은 줄 단위로 나눠 여러 번 보낸다.
링크(web_url)는 카카오 디벨로퍼스 [제품 링크 관리 > 웹 도메인]에 등록한 도메인이어야 한다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode

from ..core.timeutil import now
from .http import HttpFunc, http_request

log = logging.getLogger(__name__)

AUTH_HOST = "https://kauth.kakao.com"
API_HOST = "https://kapi.kakao.com"
TEXT_LIMIT = 200

K_ACCESS = "kakao_access_token"
K_REFRESH = "kakao_refresh_token"
K_USER = "kakao_user"
K_CONNECTED = "kakao_connected_at"


class KakaoError(Exception):
    def __init__(self, message: str, *, code: int | None = None, need_reconnect: bool = False):
        super().__init__(message)
        self.code = code
        self.need_reconnect = need_reconnect


class KakaoClient:
    def __init__(self, *, rest_api_key: str, client_secret: str, redirect_uri: str, tokens, http: HttpFunc = http_request):
        self.rest_api_key = rest_api_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.tokens = tokens  # TokenRepo
        self.http = http

    @property
    def configured(self) -> bool:
        return bool(self.rest_api_key)

    # ---------------------------------------------------------------- 연결
    def authorize_url(self, state: str) -> str:
        q = {
            "client_id": self.rest_api_key,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "talk_message",
            "state": state,
        }
        return f"{AUTH_HOST}/oauth/authorize?{urlencode(q)}"

    def exchange_code(self, code: str) -> dict:
        res = self.http(
            "POST",
            f"{AUTH_HOST}/oauth/token",
            form={
                "grant_type": "authorization_code",
                "client_id": self.rest_api_key,
                "redirect_uri": self.redirect_uri,
                "code": code,
                "client_secret": self.client_secret or None,
            },
        )
        data = res.json()
        if not res.ok or "access_token" not in data:
            raise KakaoError(f"카카오 로그인 실패: {data.get('error_description') or data}")
        self._save_tokens(data, connected=True)
        nickname = self._fetch_nickname(data["access_token"])
        if nickname:
            self.tokens.set_many({K_USER: (nickname, None)})
        return {"nickname": nickname}

    def _fetch_nickname(self, access_token: str) -> str:
        """연결 직후 사용자 정보 조회 (누가 연결했는지 화면에 보여주기 위함)."""
        res = self.http("GET", f"{API_HOST}/v2/user/me", headers={"Authorization": f"Bearer {access_token}"})
        if not res.ok:
            return ""
        data = res.json()
        return ((data.get("kakao_account") or {}).get("profile") or {}).get("nickname") or (data.get("properties") or {}).get("nickname") or ""

    def _save_tokens(self, data: dict, *, connected: bool = False) -> None:
        t = now()
        values: dict[str, tuple[str, datetime | None]] = {
            K_ACCESS: (data["access_token"], t + timedelta(seconds=int(data.get("expires_in", 0)))),
        }
        if data.get("refresh_token"):  # 갱신 응답에는 남은 기간이 1개월 미만일 때만 들어 있다
            values[K_REFRESH] = (
                data["refresh_token"],
                t + timedelta(seconds=int(data.get("refresh_token_expires_in", 0))),
            )
        if connected:
            values[K_CONNECTED] = (t.isoformat(), None)
        self.tokens.set_many(values)

    def disconnect(self) -> None:
        self.tokens.delete_keys([K_ACCESS, K_REFRESH, K_USER, K_CONNECTED])

    def status(self) -> dict:
        refresh, refresh_exp = self.tokens.get_entry(K_REFRESH)
        user, _ = self.tokens.get_entry(K_USER)
        connected_at, _ = self.tokens.get_entry(K_CONNECTED)
        connected = bool(refresh) and (refresh_exp is None or refresh_exp > now())
        return {
            "configured": self.configured,
            "connected": connected,
            "nickname": user,
            "connected_at": connected_at or None,
            "refresh_expires_at": refresh_exp.isoformat() if refresh_exp else None,
        }

    # ---------------------------------------------------------------- 토큰
    def refresh(self) -> dict:
        refresh_token, refresh_exp = self.tokens.get_entry(K_REFRESH)
        if not refresh_token:
            raise KakaoError("카카오가 연결돼 있지 않아요. 설정 화면에서 [카카오 연결]을 눌러 주세요.", need_reconnect=True)
        if refresh_exp and refresh_exp < now():
            raise KakaoError("카카오 연결이 만료됐어요. [카카오 연결]을 다시 눌러 주세요.", need_reconnect=True)
        res = self.http(
            "POST",
            f"{AUTH_HOST}/oauth/token",
            form={
                "grant_type": "refresh_token",
                "client_id": self.rest_api_key,
                "refresh_token": refresh_token,
                "client_secret": self.client_secret or None,
            },
        )
        data = res.json()
        if not res.ok or "access_token" not in data:
            raise KakaoError(
                f"카카오 토큰 갱신 실패: {data.get('error_description') or data.get('msg') or data}",
                need_reconnect=res.status in (400, 401),
            )
        self._save_tokens(data)
        return {"refreshed": True, "new_refresh_token": bool(data.get("refresh_token"))}

    def access_token(self) -> str:
        token, exp = self.tokens.get_entry(K_ACCESS)
        if not token or not exp or exp - timedelta(minutes=10) < now():
            self.refresh()
            token, _ = self.tokens.get_entry(K_ACCESS)
        return token

    # ---------------------------------------------------------------- 발송
    def send_text(self, text: str, *, link_url: str, button_title: str = "열어보기") -> int:
        """긴 글은 줄 단위로 200자씩 나눠 보낸다. 보낸 메시지 수를 돌려준다."""
        if not self.configured:
            raise KakaoError("KAKAO_REST_API_KEY 가 설정되지 않았어요.")
        chunks = split_text(text, TEXT_LIMIT)
        for i, chunk in enumerate(chunks):
            self._send_one(chunk, link_url=link_url, button_title=button_title if i == len(chunks) - 1 else "")
        return len(chunks)

    def _send_one(self, text: str, *, link_url: str, button_title: str, retried: bool = False) -> None:
        tpl: dict = {"object_type": "text", "text": text, "link": {"web_url": link_url, "mobile_web_url": link_url}}
        if button_title:
            tpl["button_title"] = button_title
        res = self.http(
            "POST",
            f"{API_HOST}/v2/api/talk/memo/default/send",
            headers={"Authorization": f"Bearer {self.access_token()}"},
            form={"template_object": json.dumps(tpl, ensure_ascii=False)},
        )
        data = res.json()
        if res.ok and data.get("result_code") == 0:
            return
        code = data.get("code")
        if code == -401 and not retried:  # 토큰이 그새 만료됨 → 갱신 후 한 번 더
            self.refresh()
            return self._send_one(text, link_url=link_url, button_title=button_title, retried=True)
        if code == -402:
            raise KakaoError("카카오톡 메시지 전송 동의가 없어요. [카카오 연결]을 다시 눌러 동의해 주세요.", code=code, need_reconnect=True)
        raise KakaoError(f"카카오 발송 실패: {data.get('msg') or data}", code=code)


def split_text(text: str, limit: int = TEXT_LIMIT) -> list[str]:
    """줄 경계를 최대한 지키며 limit 글자 이하로 나눈다."""
    text = text.strip()
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    cur = ""
    for line in text.split("\n"):
        while len(line) > limit:  # 한 줄이 너무 길면 강제로 자른다
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{cur}\n{line}" if cur else line
        if len(candidate) > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = candidate
    if cur.strip():
        chunks.append(cur)
    return [c for c in chunks if c.strip()]
