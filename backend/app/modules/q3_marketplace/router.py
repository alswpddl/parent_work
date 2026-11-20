from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ...api.deps import get_ctx, require_admin
from ...context import AppContext
from .service import MarketConfirmIn, MarketPreview, MarketResult

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"], dependencies=[Depends(require_admin)])


@router.post("/import", response_model=MarketPreview)
async def import_preview(
    file: UploadFile = File(...),
    source: str = Form(default="auto", description="auto / smartstore / coupang"),
    ctx: AppContext = Depends(get_ctx),
) -> MarketPreview:
    data = await file.read()
    return ctx.services["marketplace"].preview(file.filename or "", data, source)


@router.post("/import/{preview_id}/confirm", response_model=MarketResult)
def import_confirm(preview_id: str, body: MarketConfirmIn, ctx: AppContext = Depends(get_ctx)) -> MarketResult:
    return ctx.services["marketplace"].confirm(preview_id, body)


@router.get("/mappings")
def mappings(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    return ctx.services["marketplace"].mappings()


@router.delete("/mappings", status_code=204)
def delete_mapping(source: str, external_name: str, ctx: AppContext = Depends(get_ctx)) -> None:
    ctx.services["marketplace"].delete_mapping(source, external_name)
