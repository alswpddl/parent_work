"""부모님(사장님) 알림 창구.

- 카카오 '나에게 보내기': 기록용 (메모라서 휴대폰이 울리지 않음)
- 웹 푸시: 홈 화면에 설치한 관리자 앱으로 '띵' 울리는 알림
둘 다 보내고, 결과는 발송기록에 남긴다.
"""

from __future__ import annotations

import logging

import re

from .kakao import KakaoClient, KakaoError
from .webpush import WebPushClient

log = logging.getLogger(__name__)


# 푸시 알림 제목 (종류 → 휴대폰 알림 맨 윗줄)
PUSH_TITLES = {
    "아침브리핑": "아침 브리핑",
    "셀프주문": "새 주문",
    "새주문": "새 주문",
    "주문취소": "주문 취소",
    "재고경고": "재고 경고",
    "월말정산": "월말 정산",
    "테스트": "테스트 알림",
    "연결확인": "카카오톡 연결",
}
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")


class OwnerNotifier:
    def __init__(self, kakao: KakaoClient, messages, web_url: str, push: WebPushClient | None = None):
        self.kakao = kakao
        self.messages = messages  # MessageLogRepo
        self.web_url = web_url
        self.push = push

    def send(self, kind: str, text: str, *, path: str = "/", button: str = "앱 열기") -> bool:
        """카카오나 푸시 중 하나라도 가면 True (예외를 던지지 않는다)."""
        pushed = self.send_push(kind, text, path=path)
        return self._send_kakao(kind, text, path=path, button=button) or pushed

    def send_push(self, kind: str, text: str, *, path: str = "/") -> bool:
        if not self.push:
            return False
        try:
            subs = self.push.subscriptions()
            if not subs:
                return False
            body = _EMOJI.sub("", text).strip()
            res = self.push.send_all(PUSH_TITLES.get(kind, kind), body, url=path, tag=kind)
        except Exception as e:  # noqa: BLE001 — 푸시 실패가 다른 일을 막지 않게
            log.warning("푸시 발송 실패(%s): %s", kind, e)
            self.messages.write(channel="앱 알림", kind=kind, to="사장님", result="실패", content=text, error=str(e))
            return False
        result = "성공" if res.sent else "실패"
        note = f"{res.sent}대 성공" + (f", {res.failed}대 실패" if res.failed else "") + (f", 끊긴 휴대폰 {res.removed}대 정리" if res.removed else "")
        self.messages.write(channel="앱 알림", kind=kind, to="사장님", result=result, content=f"[{note}] {text}")
        return res.sent > 0

    def _send_kakao(self, kind: str, text: str, *, path: str, button: str) -> bool:
        if not self.kakao.configured:
            self.messages.write(channel="카카오(나에게)", kind=kind, to="사장님", result="건너뜀", content=text, error="카카오 키 없음")
            return False
        try:
            n = self.kakao.send_text(text, link_url=f"{self.web_url}{path}", button_title=button)
            self.messages.write(channel="카카오(나에게)", kind=kind, to="사장님", result="성공", content=f"[{n}건] {text}")
            return True
        except KakaoError as e:
            log.warning("카카오 발송 실패(%s): %s", kind, e)
            self.messages.write(channel="카카오(나에게)", kind=kind, to="사장님", result="실패", content=text, error=str(e))
            return False
