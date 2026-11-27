"""토스페이먼츠 결제 승인·취소 (서버에서만 호출 — 시크릿 키는 브라우저로 절대 보내지 않는다).

흐름: 손님 브라우저가 결제위젯으로 인증 → successUrl 로 paymentKey·orderId·amount 를 받음
→ 우리 서버가 주문 금액과 같은지 확인한 뒤 → 여기 confirm() 으로 최종 승인.
카드 번호·CVC 같은 결제 정보는 토스 결제창에서만 입력되고 우리 서버·시트에는 남지 않는다.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

from .http import HttpFunc, http_request

log = logging.getLogger(__name__)
API = "https://api.tosspayments.com/v1/payments"


@dataclass
class TossResult:
    ok: bool
    data: dict[str, Any]
    message: str = ""

    @property
    def method(self) -> str:
        """결제수단 한글: 카드 / 간편결제(토스페이) / 계좌이체 / 가상계좌 …"""
        m = str(self.data.get("method") or "")
        easy = (self.data.get("easyPay") or {}).get("provider") if isinstance(self.data.get("easyPay"), dict) else ""
        card = (self.data.get("card") or {}).get("issuerCode") if isinstance(self.data.get("card"), dict) else ""
        if m == "간편결제" and easy:
            return f"간편결제({easy})"
        if m == "카드" and card:
            return "카드"
        return m


class TossClient:
    def __init__(self, secret_key: str, http: HttpFunc = http_request) -> None:
        self.secret_key = secret_key
        self.http = http

    def _headers(self, idem: str = "") -> dict[str, str]:
        token = base64.b64encode(f"{self.secret_key}:".encode()).decode()
        h = {"Authorization": f"Basic {token}"}
        if idem:
            h["Idempotency-Key"] = idem  # 같은 요청이 두 번 가도 한 번만 처리
        return h

    def _call(self, url: str, body: dict[str, Any], idem: str = "") -> TossResult:
        try:
            r = self.http("POST", url, headers=self._headers(idem), json_body=body, timeout=20)
        except Exception as e:  # 네트워크 오류
            log.warning("토스페이먼츠 호출 실패: %s", e)
            return TossResult(False, {}, "결제 서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.")
        data = r.json() if r.body else {}
        if not isinstance(data, dict):
            data = {}
        if r.ok:
            return TossResult(True, data)
        return TossResult(False, data, str(data.get("message") or f"결제 처리 실패 ({r.status})"))

    def confirm(self, payment_key: str, order_id: str, amount: int) -> TossResult:
        return self._call(
            f"{API}/confirm",
            {"paymentKey": payment_key, "orderId": order_id, "amount": amount},
            idem=f"confirm-{payment_key}",
        )

    def cancel(self, payment_key: str, reason: str) -> TossResult:
        return self._call(f"{API}/{payment_key}/cancel", {"cancelReason": reason[:200]}, idem=f"cancel-{payment_key}")
