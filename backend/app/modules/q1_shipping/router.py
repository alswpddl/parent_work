from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from ...api.deps import get_ctx, require_admin
from ...context import AppContext
from ...core.errors import ValidationFailed
from ...core.timeutil import today
from ...schemas.common import OPEN_STATUSES
from ...schemas.order import OrderOut
from .carriers import CARRIERS, get_format
from .dispatch_text import build_dispatch_text
from .parcel_excel import build_parcel_workbook

router = APIRouter(prefix="/api", tags=["shipping"], dependencies=[Depends(require_admin)])


class BoardOut(BaseModel):
    threshold_kg: float
    parcel: list[OrderOut]
    truck: list[OrderOut]
    parcel_kg: float
    truck_kg: float


@router.get("/shipping/board", response_model=BoardOut)
def board(ctx: AppContext = Depends(get_ctx)) -> BoardOut:
    """출고 대기(접수·출고대기) 주문을 택배/화물로 나눈 화면용 데이터."""
    st = ctx.settings.load()
    open_orders = ctx.orders.query(statuses=list(OPEN_STATUSES))
    parcel = [o for o in open_orders if o.ship_method == "택배"]
    truck = [o for o in open_orders if o.ship_method == "화물"]
    return BoardOut(
        threshold_kg=st.threshold_kg,
        parcel=parcel,
        truck=truck,
        parcel_kg=round(sum(o.order_kg for o in parcel), 1),
        truck_kg=round(sum(o.order_kg for o in truck), 1),
    )


class CarrierOut(BaseModel):
    code: str
    name: str
    verified: bool


@router.get("/shipping/carriers", response_model=list[CarrierOut])
def carriers() -> list[CarrierOut]:
    return [CarrierOut(code=f.code, name=f.name, verified=f.verified) for f in CARRIERS.values()]


class ParcelExportIn(BaseModel):
    carrier: str = Field(default="", description="비우면 _설정의 기본 택배사")
    order_ids: list[str] | None = Field(default=None, description="비우면 출고 대기 중인 택배 주문 전체")


@router.post("/shipping/parcel-export")
def parcel_export(body: ParcelExportIn, ctx: AppContext = Depends(get_ctx)) -> Response:
    st = ctx.settings.load()
    fmt = get_format(body.carrier or st.default_carrier)
    if body.order_ids:
        wanted = set(body.order_ids)
        orders = [o for o in ctx.orders.query(include_cancelled=False) if o.order_id in wanted]
    else:
        orders = ctx.orders.query(statuses=list(OPEN_STATUSES), method="택배")
    if not orders:
        raise ValidationFailed("내보낼 택배 주문이 없어요.")
    content = build_parcel_workbook(orders, fmt, st)
    filename = f"택배발송_{fmt.name}_{today():%Y%m%d}.xlsx"
    ctx.logs.write("택배 엑셀 생성", fmt.code, f"{len(orders)}건")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=\"parcel_{today():%Y%m%d}.xlsx\"; filename*=UTF-8''{quote(filename)}",
            "X-Order-Count": str(len(orders)),
        },
    )


class DispatchTextOut(BaseModel):
    order_id: str
    text: str


@router.get("/shipping/{order_id}/dispatch-text", response_model=DispatchTextOut)
def dispatch_text(order_id: str, ctx: AppContext = Depends(get_ctx)) -> DispatchTextOut:
    o = ctx.orders.get(order_id)
    return DispatchTextOut(order_id=order_id, text=build_dispatch_text(o, ctx.settings.load()))


@router.post("/shipping/{order_id}/ship", response_model=OrderOut)
def ship(order_id: str, ctx: AppContext = Depends(get_ctx)) -> OrderOut:
    """출고 완료 → order.shipped 이벤트 (3분기 알림톡, 4분기 재고 차감이 구독)."""
    return ctx.orders.ship(order_id)


@router.post("/shipping/{order_id}/unship", response_model=OrderOut)
def unship(order_id: str, ctx: AppContext = Depends(get_ctx)) -> OrderOut:
    """실수로 누른 출고 완료 되돌리기 → order.unshipped 이벤트."""
    return ctx.orders.unship(order_id)
