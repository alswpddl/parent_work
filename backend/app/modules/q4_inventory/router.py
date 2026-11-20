from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...api.deps import get_ctx, require_admin
from ...context import AppContext
from .service import AdjustIn, ItemIn, ItemOut, ItemPatch, MoveOut, ReceiveIn

router = APIRouter(prefix="/api/inventory", tags=["inventory"], dependencies=[Depends(require_admin)])


def _svc(ctx: AppContext):
    return ctx.services["inventory"]


@router.get("", response_model=list[ItemOut])
def list_items(ctx: AppContext = Depends(get_ctx)) -> list[ItemOut]:
    return _svc(ctx).list_items()


@router.post("", response_model=ItemOut, status_code=201)
def create_item(body: ItemIn, ctx: AppContext = Depends(get_ctx)) -> ItemOut:
    return _svc(ctx).create(body)


@router.get("/moves", response_model=list[MoveOut])
def moves(item_id: str = "", limit: int = Query(default=100, le=500), ctx: AppContext = Depends(get_ctx)) -> list[MoveOut]:
    return _svc(ctx).recent_moves(item_id or None, limit)


@router.post("/check")
def check(ctx: AppContext = Depends(get_ctx)) -> dict:
    """지금 바로 점검하고 부족하면 카톡 경고 (오늘 이미 보냈어도 다시)."""
    return _svc(ctx).check_and_alert(force=True)


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(item_id: str, body: ItemPatch, ctx: AppContext = Depends(get_ctx)) -> ItemOut:
    return _svc(ctx).update(item_id, body)


@router.post("/{item_id}/receive", response_model=ItemOut)
def receive(item_id: str, body: ReceiveIn, ctx: AppContext = Depends(get_ctx)) -> ItemOut:
    return _svc(ctx).receive(item_id, body)


@router.post("/{item_id}/adjust", response_model=ItemOut)
def adjust(item_id: str, body: AdjustIn, ctx: AppContext = Depends(get_ctx)) -> ItemOut:
    return _svc(ctx).adjust(item_id, body)
