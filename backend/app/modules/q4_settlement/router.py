from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Response

from ...api.deps import get_ctx, require_admin
from ...context import AppContext
from ...core.errors import NotFoundError
from ...core.signing import verify
from .service import GenerateIn, GenerateOut, SendIn, SendOut, SettlementOut, SettlementPatch

router = APIRouter(prefix="/api/settlements", tags=["settlement"], dependencies=[Depends(require_admin)])
public_router = APIRouter(prefix="/api/public", tags=["public"])


def _svc(ctx: AppContext):
    return ctx.services["settlement"]


def _pdf_response(filename: str, data: bytes, inline: bool = True) -> Response:
    disp = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"{disp}; filename=\"statement.pdf\"; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("", response_model=list[SettlementOut])
def list_settlements(period: str = "", ctx: AppContext = Depends(get_ctx)) -> list[SettlementOut]:
    return _svc(ctx).list_settlements(period or None)


@router.post("/generate", response_model=GenerateOut)
def generate(body: GenerateIn, ctx: AppContext = Depends(get_ctx)) -> GenerateOut:
    return _svc(ctx).generate(body)


@router.post("/send-all", response_model=list[SendOut])
def send_all(period: str, body: SendIn, ctx: AppContext = Depends(get_ctx)) -> list[SendOut]:
    return _svc(ctx).send_all(period, body)


@router.get("/{settlement_id}", response_model=SettlementOut)
def get_settlement(settlement_id: str, ctx: AppContext = Depends(get_ctx)) -> SettlementOut:
    return _svc(ctx).get(settlement_id)


@router.patch("/{settlement_id}", response_model=SettlementOut)
def patch_settlement(settlement_id: str, body: SettlementPatch, ctx: AppContext = Depends(get_ctx)) -> SettlementOut:
    return _svc(ctx).update(settlement_id, body)


@router.get("/{settlement_id}/pdf")
def pdf(settlement_id: str, download: bool = False, ctx: AppContext = Depends(get_ctx)) -> Response:
    filename, data = _svc(ctx).pdf(settlement_id)
    return _pdf_response(filename, data, inline=not download)


@router.get("/{settlement_id}/link")
def link(settlement_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    """거래처에 직접 보낼 수 있는 PDF 링크 (30일 유효, 로그인 불필요)."""
    _svc(ctx).get(settlement_id)
    return {"url": _svc(ctx).public_link(settlement_id)}


@router.post("/{settlement_id}/send", response_model=SendOut)
def send(settlement_id: str, body: SendIn, ctx: AppContext = Depends(get_ctx)) -> SendOut:
    return _svc(ctx).send(settlement_id, body)


@public_router.get("/statements/{token}")
def public_statement(token: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    payload = verify(ctx.config.auth_secret, token)
    if not payload or not payload.startswith("stmt:"):
        raise NotFoundError("링크가 만료됐어요. 공장에 다시 요청해 주세요.")
    filename, data = _svc(ctx).pdf(payload[5:])
    return _pdf_response(filename, data)
