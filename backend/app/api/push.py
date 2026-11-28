"""관리자 앱 휴대폰 알림(웹 푸시) 켜고 끄기."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..context import AppContext
from ..core.errors import ValidationFailed
from .deps import get_ctx, require_admin

router = APIRouter(prefix="/api/push", tags=["push"], dependencies=[Depends(require_admin)])


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=10, max_length=60)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    keys: PushKeys
    label: str = Field(default="", max_length=40)


class EndpointIn(BaseModel):
    endpoint: str = Field(default="", max_length=1000)


class PushStatus(BaseModel):
    public_key: str
    devices: int
    subscribed: bool = False
    dev: bool = False  # 이 휴대폰이 서버 오류 알림(개발자용)도 받는지


class DevIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    dev: bool


def _push(ctx: AppContext):
    if not ctx.push:
        raise ValidationFailed("휴대폰 알림을 쓸 수 없는 서버 설정이에요.")
    return ctx.push


@router.post("/status")
def status(body: EndpointIn, ctx: AppContext = Depends(get_ctx)) -> PushStatus:
    p = _push(ctx)
    subs = p.subscriptions()
    me = next((s for s in subs if s.get("endpoint") == body.endpoint), None)
    return PushStatus(public_key=p.public_key(), devices=len(subs), subscribed=me is not None, dev=bool(me and me.get("dev")))


@router.post("/subscribe")
def subscribe(body: SubscriptionIn, ctx: AppContext = Depends(get_ctx)) -> PushStatus:
    p = _push(ctx)
    try:
        p.subscribe(body.endpoint, body.keys.p256dh, body.keys.auth, label=body.label)
    except ValueError as e:
        raise ValidationFailed(str(e)) from e
    ctx.logs.write("휴대폰 알림 켬", body.label or "휴대폰")
    return PushStatus(public_key=p.public_key(), devices=len(p.subscriptions()), subscribed=True)


@router.post("/unsubscribe")
def unsubscribe(body: EndpointIn, ctx: AppContext = Depends(get_ctx)) -> PushStatus:
    p = _push(ctx)
    if body.endpoint:
        p.unsubscribe(body.endpoint)
    return PushStatus(public_key=p.public_key(), devices=len(p.subscriptions()), subscribed=False)


@router.post("/dev")
def set_dev(body: DevIn, ctx: AppContext = Depends(get_ctx)) -> PushStatus:
    p = _push(ctx)
    if not p.set_dev(body.endpoint, body.dev):
        raise ValidationFailed("이 휴대폰은 아직 알림을 켜지 않았어요. 먼저 '이 휴대폰으로 알림 받기'를 눌러 주세요.")
    return PushStatus(public_key=p.public_key(), devices=len(p.subscriptions()), subscribed=True, dev=body.dev)


@router.post("/dev-test")
def dev_test(ctx: AppContext = Depends(get_ctx)) -> dict:
    res = _push(ctx).send_all("서버 오류 알림 시험", "이렇게 서버에 문제가 생기면 이 휴대폰에만 알려 드려요.", url="/settings?tab=system", tag="dev-test", dev_only=True)
    return {"sent": res.sent}


@router.post("/test")
def test(ctx: AppContext = Depends(get_ctx)) -> dict:
    p = _push(ctx)
    res = p.send_all("테스트 알림", "휴대폰 알림이 잘 와요. 아침 브리핑과 새 주문도 이렇게 울려요.", url="/", tag="테스트")
    return {"sent": res.sent, "failed": res.failed, "removed": res.removed}
