"""부모님(사장님) 알림 창구. 카카오 '나에게 보내기'를 쓰고, 결과는 발송기록에 남긴다."""

from __future__ import annotations

import logging

from .kakao import KakaoClient, KakaoError

log = logging.getLogger(__name__)


class OwnerNotifier:
    def __init__(self, kakao: KakaoClient, messages, web_url: str):
        self.kakao = kakao
        self.messages = messages  # MessageLogRepo
        self.web_url = web_url

    def send(self, kind: str, text: str, *, path: str = "/", button: str = "앱 열기") -> bool:
        """성공하면 True. 카카오가 연결되지 않았거나 실패하면 False (예외를 던지지 않는다)."""
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
