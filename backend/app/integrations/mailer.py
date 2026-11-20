"""SMTP 메일 발송 (거래명세표 PDF 첨부).

Gmail 을 쓴다면: 구글 계정 2단계 인증 → '앱 비밀번호' 생성 → SMTP_PASSWORD 에 넣기
  SMTP_HOST=smtp.gmail.com  SMTP_PORT=465  SMTP_USER=보내는주소@gmail.com
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Callable


class MailError(Exception):
    pass


class Mailer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        sender: str = "",
        smtp_factory: Callable[..., smtplib.SMTP] | None = None,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender or user
        self._factory = smtp_factory

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.password)

    def build(self, *, to: str, subject: str, body: str, attachments: list[tuple[str, bytes, str]] | None = None) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        for filename, data, mime in attachments or []:
            maintype, subtype = mime.split("/", 1)
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
        return msg

    def send(self, *, to: str, subject: str, body: str, attachments: list[tuple[str, bytes, str]] | None = None) -> None:
        if not self.configured:
            raise MailError("메일(SMTP) 설정이 비어 있어요.")
        if "@" not in (to or ""):
            raise MailError(f"이메일 주소가 올바르지 않아요: {to or '(없음)'}")
        msg = self.build(to=to, subject=subject, body=body, attachments=attachments)
        try:
            if self._factory:
                smtp = self._factory(self.host, self.port)
            elif self.port == 465:
                smtp = smtplib.SMTP_SSL(self.host, self.port, context=ssl.create_default_context(), timeout=20)
            else:
                smtp = smtplib.SMTP(self.host, self.port, timeout=20)
                smtp.starttls(context=ssl.create_default_context())
            with smtp:
                smtp.login(self.user, self.password)
                smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as e:
            raise MailError(f"메일 발송 실패: {e}") from e
