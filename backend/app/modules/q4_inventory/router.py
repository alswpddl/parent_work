from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from ...api.deps import get_ctx, require_admin
from ...context import AppContext
from .service import AdjustIn, ItemIn, ItemOut, ItemPatch, MoveOut, NeedOut, ReceiveIn, StocktakeIn, StocktakeOut

router = APIRouter(prefix="/api/inventory", tags=["inventory"], dependencies=[Depends(require_admin)])
tanks_router = APIRouter(prefix="/api/inventory/tanks", tags=["inventory"], dependencies=[Depends(require_admin)])


def _svc(ctx: AppContext):
    return ctx.services["inventory"]


@router.get("", response_model=list[ItemOut])
def list_items(ctx: AppContext = Depends(get_ctx)) -> list[ItemOut]:
    return _svc(ctx).list_items()


@router.post("", response_model=ItemOut, status_code=201)
def create_item(body: ItemIn, ctx: AppContext = Depends(get_ctx)) -> ItemOut:
    return _svc(ctx).create(body)


@router.get("/needs", response_model=list[NeedOut])
def needs(until: date | None = Query(default=None, description="이 날까지 받는 주문 (비우면 출고 전 전부)"), ctx: AppContext = Depends(get_ctx)) -> list[NeedOut]:
    """출고 전 주문들이 쓸 자재·저장고 젓갈 vs 지금 재고 (오늘의 할당량 화면용)"""
    return _svc(ctx).needs(until)


@router.post("/stocktake", response_model=StocktakeOut)
def stocktake(body: StocktakeIn, ctx: AppContext = Depends(get_ctx)) -> StocktakeOut:
    """재고 한꺼번에 입력"""
    return _svc(ctx).stocktake(body)


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


# ---------------------------------------------------------------- 숙성 저장소 지도
from .aging import BuildingIn, TankMapOut, TankOut, TankPatch  # noqa: E402


@tanks_router.get("", response_model=TankMapOut)
def tank_map(ctx: AppContext = Depends(get_ctx)) -> TankMapOut:
    """건물별 저장소와 숙성 단계 (숙성 끝 · 숙성 중 · 비어 있음)"""
    return ctx.services["aging"].map()


@tanks_router.post("/buildings", response_model=TankMapOut, status_code=201)
def add_building(body: BuildingIn, ctx: AppContext = Depends(get_ctx)) -> TankMapOut:
    return ctx.services["aging"].add_building(body)


@tanks_router.delete("/buildings/{name}", response_model=TankMapOut)
def delete_building(name: str, ctx: AppContext = Depends(get_ctx)) -> TankMapOut:
    return ctx.services["aging"].delete_building(name)


@tanks_router.patch("/{tank_id}", response_model=TankOut)
def update_tank(tank_id: str, body: TankPatch, ctx: AppContext = Depends(get_ctx)) -> TankOut:
    return ctx.services["aging"].update(tank_id, body)

