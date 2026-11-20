from __future__ import annotations

from fastapi import APIRouter, Depends

from ...api.deps import get_ctx, require_admin
from ...context import AppContext
from .service import ReorderStat, SnoozeIn

router = APIRouter(prefix="/api/reorder", tags=["reorder"], dependencies=[Depends(require_admin)])


@router.get("/reminders", response_model=list[ReorderStat])
def reminders(ctx: AppContext = Depends(get_ctx)) -> list[ReorderStat]:
    return ctx.services["reorder"].reminders()


@router.get("/stats", response_model=list[ReorderStat])
def stats(ctx: AppContext = Depends(get_ctx)) -> list[ReorderStat]:
    return ctx.services["reorder"].stats()


@router.post("/recompute")
def recompute(ctx: AppContext = Depends(get_ctx)) -> dict:
    return ctx.services["reorder"].job()


@router.post("/{customer_id}/snooze", response_model=ReorderStat)
def snooze(customer_id: str, body: SnoozeIn, ctx: AppContext = Depends(get_ctx)) -> ReorderStat:
    return ctx.services["reorder"].snooze(customer_id, body)
