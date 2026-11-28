"""솔라피(SOLAPI) 카카오 알림톡 — 거래처 담당자에게 출고·명세서 안내.

- 인증: Authorization: HMAC-SHA256 apiKey=..., date=..., salt=..., signature=...
  signature = HMAC-SHA256(API Secret, date + salt) 의 hex
- 발송: POST https://api.solapi.com/messages/v4/send-many/detail
- 알림톡은 카카오 비즈니스 채널 + 사전 승인된 템플릿이 있어야 한다.
  템플릿 문구는 docs/알림톡_템플릿.md 참고. 변수 키는 '#{변수명}' 형태, 값은 모두 문자열.
- 대체발송: disableSms=false 와 발신번호(from)가 있으면 알림톡 실패 시 문자로 보낸다.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timezone

from .http import HttpFunc, http_request

log = logging.getLogger(__name__)

API_URL = "https://api.solapi.com/messages/v4/send-many/detail"


class SolapiError(Exception):
    pass


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def is_mobile(phone: str) -> bool:
    return bool(re.fullmatch(r"01[016789]\d{7,8}", normalize_phone(phone)))


class SolapiClient:
    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        sender: str,
        pfid: str,
        sms_fallback: bool = True,
        http: HttpFunc = http_request,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.sender = normalize_phone(sender)
        self.pfid = pfid
        self.sms_fallback = sms_fallback
        self.http = http

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret and self.pfid)

    @property
    def sms_ready(self) -> bool:
        """문자(SMS) 발송 준비: 키·시크릿 + 솔라피에 등록한 발신번호 (알림톡 채널 없어도 됨)"""
        return bool(self.api_key and self.api_secret and self.sender)

    def send_sms(self, *, to: str, text: str) -> dict:
        if not self.sms_ready:
            raise SolapiError("문자 발송 설정(API 키·시크릿·발신번호)이 비어 있어요.")
        if not is_mobile(to):
            raise SolapiError("휴대폰 번호가 아니라 문자를 보낼 수 없어요.")
        body = {"messages": [{"to": normalize_phone(to), "from": self.sender, "text": text}]}
        res = self.http("POST", API_URL, headers={"Authorization": self.auth_header()}, json_body=body)
        data = res.json()
        if not res.ok:
            raise SolapiError(f"솔라피 오류({res.status}): {data.get('errorMessage') or data.get('message') or data}")
        failed = data.get("failedMessageList") or []
        if failed:
            raise SolapiError(f"문자 발송 실패: {failed[0].get('statusMessage') or failed[0].get('reason') or failed}")
        return {"group_id": (data.get("groupInfo") or {}).get("groupId", "")}

    def auth_header(self, *, date: str | None = None, salt: str | None = None) -> str:
        date = date or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        salt = salt or secrets.token_hex(16)
        sig = hmac.new(self.api_secret.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
        return f"HMAC-SHA256 apiKey={self.api_key}, date={date}, salt={salt}, signature={sig}"

    def build_alimtalk(self, *, to: str, template_id: str, variables: dict[str, str]) -> dict:
        kakao: dict = {
            "pfId": self.pfid,
            "templateId": template_id,
            "variables": {(k if k.startswith("#{") else f"#{{{k}}}"): str(v) for k, v in variables.items()},
        }
        msg: dict = {"to": normalize_phone(to), "kakaoOptions": kakao}
        if self.sms_fallback and self.sender:
            kakao["disableSms"] = False
            msg["from"] = self.sender
        else:
            kakao["disableSms"] = True
        return msg

    def send_alimtalk(self, *, to: str, template_id: str, variables: dict[str, str]) -> dict:
        if not self.configured:
            raise SolapiError("솔라피 설정(API 키·시크릿·채널 ID)이 비어 있어요.")
        if not template_id:
            raise SolapiError("알림톡 템플릿 ID 가 설정되지 않았어요.")
        if not is_mobile(to):
            raise SolapiError(f"휴대폰 번호가 아니라 알림톡을 보낼 수 없어요: {to or '(없음)'}")
        body = {"messages": [self.build_alimtalk(to=to, template_id=template_id, variables=variables)]}
        res = self.http("POST", API_URL, headers={"Authorization": self.auth_header()}, json_body=body)
        data = res.json()
        if not res.ok:
            raise SolapiError(f"솔라피 오류({res.status}): {data.get('errorMessage') or data.get('message') or data}")
        failed = data.get("failedMessageList") or []
        if failed:
            reason = failed[0].get("statusMessage") or failed[0].get("reason") or failed
            raise SolapiError(f"알림톡 발송 실패: {reason}")
        return {"group_id": (data.get("groupInfo") or {}).get("groupId", "")}
