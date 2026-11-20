from __future__ import annotations

from fastapi import APIRouter, Depends

from ...api.deps import get_ctx, require_admin
from ...context import AppContext
from .service import NotifyResult
from .templates import TEMPLATES

router = APIRouter(prefix="/api/notify", tags=["notify"], dependencies=[Depends(require_admin)])


@router.get("/status")
def status(ctx: AppContext = Depends(get_ctx)) -> dict:
    return ctx.services["notify"].status()


@router.get("/templates")
def templates() -> dict:
    """솔라피에 등록할 알림톡 템플릿 원문 (복사해서 쓰기)."""
    return TEMPLATES


@router.get("/{order_id}/preview", response_model=NotifyResult)
def preview(order_id: str, ctx: AppContext = Depends(get_ctx)) -> NotifyResult:
    return ctx.services["notify"].preview(ctx.orders.get(order_id))


@router.post("/{order_id}/send", response_model=NotifyResult)
def send(order_id: str, ctx: AppContext = Depends(get_ctx)) -> NotifyResult:
    """[다시 보내기] — 이미 보낸 주문도 한 번 더 보낸다."""
    return ctx.services["notify"].notify_shipment(ctx.orders.get(order_id, fresh=True), force=True)
