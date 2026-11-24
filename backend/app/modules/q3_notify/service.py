"""거래처 출고 알림톡.

언제 보내나
- 택배: 송장번호가 있을 때 (보통 운송장 역등록 순간). 송장 없이 '출고 완료'만 누르면 기다렸다가 송장이 들어오면 보낸다.
- 화물: 차량번호가 있을 때.
- 이미 보낸 주문(알림발송 칸이 찬 주문)은 다시 보내지 않는다. [다시 보내기]는 force=True.
- _설정 '거래처 출고 알림톡 보내기' = 아니오 이거나, 거래처 '알림톡수신' = FALSE 면 보내지 않는다.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel

from ...core.timeutil import fmt_date_ko, now
from ...integrations.solapi import SolapiError, is_mobile
from ...schemas.order import OrderOut
from .templates import TEMPLATES, render

log = logging.getLogger(__name__)


class NotifyResult(BaseModel):
    sent: bool
    kind: str = ""
    reason: str = ""
    preview: str = ""


def tracking_link(carrier: str, tracking_no: str) -> str:
    return f"https://search.naver.com/search.naver?query={quote(f'{carrier} {tracking_no}')}"


def items_text(o: OrderOut, limit: int = 100) -> str:
    s = ", ".join(f"{l.product_name} {l.qty}개" for l in o.lines)
    return s if len(s) <= limit else s[: limit - 3] + "..."


class NotifyService:
    def __init__(self, ctx: Any):
        self.ctx = ctx

    def template_id(self, kind: str) -> str:
        c = self.ctx.config
        return {
            "parcel": c.solapi_tpl_parcel,
            "truck": c.solapi_tpl_truck,
            "statement": c.solapi_tpl_statement,
            "order_received": c.solapi_tpl_order_received,
        }.get(kind, "")

    def status(self) -> dict:
        return {
            "configured": self.ctx.solapi.configured,
            "enabled": self.ctx.settings.load().notify_customers,
            "templates": {k: {"name": v["name"], "env": v["env"], "ready": bool(self.template_id(k))} for k, v in TEMPLATES.items()},
            "sms_fallback": self.ctx.config.solapi_sms_fallback and bool(self.ctx.config.solapi_sender),
        }

    # ---------------------------------------------------------------- 변수
    def _base_vars(self, customer_name: str) -> dict[str, str]:
        st = self.ctx.settings.load()
        return {"공장명": st.factory_name or "공장", "공장전화": st.factory_phone or "-", "거래처명": customer_name}

    def shipment_vars(self, o: OrderOut) -> tuple[str, dict[str, str]]:
        v = self._base_vars(o.customer_name)
        v.update({"주문번호": o.order_id, "품목": items_text(o)})
        if o.ship_method == "화물":
            v.update(
                {
                    "중량": f"{o.order_kg:g}kg",
                    "차량번호": o.truck_no or "-",
                    "기사연락처": o.driver_phone or "-",
                    "도착예정": fmt_date_ko(o.due_date),
                }
            )
            return "truck", v
        v.update(
            {
                "택배사": o.carrier or "-",
                "송장번호": o.tracking_no or "-",
                "조회링크": tracking_link(o.carrier, o.tracking_no) if o.tracking_no else "-",
            }
        )
        return "parcel", v

    def preview(self, o: OrderOut) -> NotifyResult:
        kind, v = self.shipment_vars(o)
        return NotifyResult(sent=False, kind=kind, preview=render(kind, v))

    # ---------------------------------------------------------------- 발송
    def _recipient(self, o: OrderOut) -> tuple[str, str]:
        """(전화번호, 건너뛸 이유)"""
        if o.customer_id:
            c = self.ctx.customers.by_id(o.customer_id)
            if c and not c.notify_opt_in:
                return "", "거래처가 알림톡 수신을 꺼 두었어요"
            phone = o.phone or (c.phone if c else "")
        else:
            phone = o.phone
        if not is_mobile(phone):
            return "", f"휴대폰 번호가 없어요 ({phone or '빈칸'})"
        return phone, ""

    def notify_shipment(self, o: OrderOut, *, force: bool = False) -> NotifyResult:
        kind, v = self.shipment_vars(o)
        text = render(kind, v)
        skip = ""
        if not force and o.notified_at:
            skip = "이미 보냈어요"
        elif o.status != "출고완료":
            skip = "아직 출고 전이에요"
        elif kind == "parcel" and not o.tracking_no:
            skip = "송장번호가 들어오면 보낼게요"
        elif kind == "truck" and not o.truck_no:
            skip = "차량번호가 들어오면 보낼게요"
        elif not force and not self.ctx.settings.load().notify_customers:
            skip = "설정에서 알림톡이 꺼져 있어요"
        elif not self.ctx.solapi.configured:
            skip = "솔라피 설정이 없어요"
        elif not self.template_id(kind):
            skip = f"{TEMPLATES[kind]['env']} 가 비어 있어요"
        phone = ""
        if not skip:
            phone, skip = self._recipient(o)
        if skip:
            return NotifyResult(sent=False, kind=kind, reason=skip, preview=text)

        label = "택배출고" if kind == "parcel" else "화물출고"
        try:
            self.ctx.solapi.send_alimtalk(to=phone, template_id=self.template_id(kind), variables=v)
        except SolapiError as e:
            self.ctx.messages.write(channel="알림톡", kind=label, to=phone, order_id=o.order_id, result="실패", content=text, error=str(e))
            return NotifyResult(sent=False, kind=kind, reason=str(e), preview=text)
        self.ctx.messages.write(channel="알림톡", kind=label, to=phone, order_id=o.order_id, result="성공", content=text)
        self.ctx.orders.set_fields(o.order_id, {"notified_at": now()}, publish=None)
        return NotifyResult(sent=True, kind=kind, preview=text)

    def send_template(self, *, kind: str, to: str, variables: dict[str, str], label: str, ref: str = "") -> NotifyResult:
        """다른 모듈(정산 등)이 쓰는 일반 발송."""
        text = render(kind, variables)
        if not self.ctx.solapi.configured:
            return NotifyResult(sent=False, kind=kind, reason="솔라피 설정이 없어요", preview=text)
        if not self.template_id(kind):
            return NotifyResult(sent=False, kind=kind, reason=f"{TEMPLATES[kind]['env']} 가 비어 있어요", preview=text)
        try:
            self.ctx.solapi.send_alimtalk(to=to, template_id=self.template_id(kind), variables=variables)
        except SolapiError as e:
            self.ctx.messages.write(channel="알림톡", kind=label, to=to, order_id=ref, result="실패", content=text, error=str(e))
            return NotifyResult(sent=False, kind=kind, reason=str(e), preview=text)
        self.ctx.messages.write(channel="알림톡", kind=label, to=to, order_id=ref, result="성공", content=text)
        return NotifyResult(sent=True, kind=kind, preview=text)

    # ---------------------------------------------------------------- 이벤트
    def on_shipped(self, payload: dict) -> None:
        r = self.notify_shipment(payload["order"])
        if not r.sent:
            log.info("알림톡 보류 %s: %s", payload["order"].order_id, r.reason)

    def on_created(self, payload: dict) -> None:
        o: OrderOut = payload["order"]
        if o.source not in ("셀프주문", "웹주문서") or not self.template_id("order_received"):
            return
        phone, skip = self._recipient(o)
        if skip:
            return
        v = self._base_vars(o.customer_name)
        v.update({"주문번호": o.order_id, "품목": items_text(o), "납기": fmt_date_ko(o.due_date)})
        self.send_template(kind="order_received", to=phone, variables=v, label="주문접수", ref=o.order_id)
