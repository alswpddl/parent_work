from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ...api.deps import get_ctx, require_admin
from ...context import AppContext
from ...schemas.order import OrderOut
from .service import CARRIERS, TrackingConfirmIn, TrackingIn, TrackingPreview, TrackingResult, TruckIn

router = APIRouter(prefix="/api", tags=["tracking"], dependencies=[Depends(require_admin)])


@router.get("/tracking/carriers", response_model=list[str])
def carriers() -> list[str]:
    return CARRIERS


@router.post("/tracking/import", response_model=TrackingPreview)
async def import_preview(
    file: UploadFile = File(...),
    carrier: str = Form(default="CJ대한통운"),
    ctx: AppContext = Depends(get_ctx),
) -> TrackingPreview:
    data = await file.read()
    return ctx.services["tracking"].preview(file.filename or "", data, carrier)


@router.post("/tracking/import/{import_id}/confirm", response_model=TrackingResult)
def import_confirm(import_id: str, body: TrackingConfirmIn, ctx: AppContext = Depends(get_ctx)) -> TrackingResult:
    return ctx.services["tracking"].confirm(import_id, body)


@router.put("/shipping/{order_id}/tracking", response_model=OrderOut)
def set_tracking(order_id: str, body: TrackingIn, ctx: AppContext = Depends(get_ctx)) -> OrderOut:
    return ctx.services["tracking"].set_tracking(order_id, body)


@router.put("/shipping/{order_id}/truck", response_model=OrderOut)
def set_truck(order_id: str, body: TruckIn, ctx: AppContext = Depends(get_ctx)) -> OrderOut:
    return ctx.services["tracking"].set_truck(order_id, body)
