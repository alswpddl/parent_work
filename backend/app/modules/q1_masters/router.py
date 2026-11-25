from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...api.deps import get_ctx, require_admin
from ...context import AppContext
from ...core.errors import NotFoundError, ValidationFailed
from ...schemas.customer import CustomerCreate, CustomerOut, CustomerPatch
from ...schemas.product import ProductCreate, ProductOut, ProductPatch
from ...schemas.settings import AppSettings, SettingsPatch
from ...services.matching import normalize

router = APIRouter(prefix="/api", tags=["masters"], dependencies=[Depends(require_admin)])


# ------------------------------------------------------------------ 설정
@router.get("/settings", response_model=AppSettings)
def get_settings(ctx: AppContext = Depends(get_ctx)) -> AppSettings:
    return ctx.settings.load()


@router.put("/settings", response_model=AppSettings)
def put_settings(body: SettingsPatch, ctx: AppContext = Depends(get_ctx)) -> AppSettings:
    out = ctx.settings.save(body)
    ctx.logs.write("설정 변경", "_설정", ", ".join(body.model_dump(exclude_none=True).keys()))
    return out


# ------------------------------------------------------------------ 거래처
@router.get("/customers", response_model=list[CustomerOut])
def list_customers(
    q: str = Query(default="", description="이름·별칭 검색"),
    include_inactive: bool = False,
    ctx: AppContext = Depends(get_ctx),
) -> list[CustomerOut]:
    items = ctx.customers.list(include_inactive=include_inactive)
    if q:
        nq = normalize(q)
        items = [c for c in items if any(nq in normalize(n) for n in [c.name, *c.alias_list()])]
    return items


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerCreate, ctx: AppContext = Depends(get_ctx)) -> CustomerOut:
    existing = ctx.customers.list(include_inactive=True, fresh=True)
    if any(normalize(c.name) == normalize(body.name) for c in existing):
        raise ValidationFailed(f"'{body.name}' 거래처가 이미 있어요.")
    cid = ctx.customers.new_id()
    ctx.customers.insert({"customer_id": cid, **body.model_dump(), "active": True})
    ctx.logs.write("거래처 추가", cid, body.name)
    out = ctx.customers.by_id(cid)
    assert out is not None
    return out


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
def patch_customer(customer_id: str, body: CustomerPatch, ctx: AppContext = Depends(get_ctx)) -> CustomerOut:
    if ctx.customers.by_id(customer_id) is None:
        raise NotFoundError("거래처를 찾을 수 없어요.")
    changes = body.model_dump(exclude_unset=True)
    if changes:
        ctx.customers.update((customer_id,), changes)
        ctx.logs.write("거래처 수정", customer_id, ", ".join(changes))
    out = ctx.customers.by_id(customer_id)
    assert out is not None
    return out


# ------------------------------------------------------------------ 품목
@router.get("/products", response_model=list[ProductOut])
def list_products(include_inactive: bool = False, ctx: AppContext = Depends(get_ctx)) -> list[ProductOut]:
    return ctx.products.list(include_inactive=include_inactive)



@router.post("/customers/{customer_id}/reset-web-password", response_model=CustomerOut)
def reset_web_password(customer_id: str, ctx: AppContext = Depends(get_ctx)) -> CustomerOut:
    """손님이 웹 주문서 비밀번호를 잊었을 때: 지우면 손님이 같은 번호로 다시 가입할 수 있다."""
    if not ctx.customers.get(customer_id, fresh=True):
        raise NotFoundError("거래처를 찾을 수 없어요.")
    ctx.customers.update((customer_id,), {"web_password": ""})
    ctx.logs.write("웹 비밀번호 초기화", customer_id, "")
    out = ctx.customers.by_id(customer_id)
    assert out is not None
    return out

@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductCreate, ctx: AppContext = Depends(get_ctx)) -> ProductOut:
    existing = ctx.products.list(include_inactive=True, fresh=True)
    sku = (body.sku or "").strip() or ctx.products.new_sku()
    if any(p.sku == sku for p in existing):
        raise ValidationFailed(f"품목코드 '{sku}' 가 이미 있어요.")
    if any(normalize(p.display_name) == normalize(f"{body.name}{body.spec}") for p in existing):
        raise ValidationFailed(f"'{body.name} {body.spec}' 품목이 이미 있어요.")
    data = body.model_dump(exclude={"sku"})
    ctx.products.insert({"sku": sku, **data, "active": True})
    ctx.logs.write("품목 추가", sku, f"{body.name} {body.spec}")
    out = ctx.products.by_sku(sku)
    assert out is not None
    return out


@router.patch("/products/{sku}", response_model=ProductOut)
def patch_product(sku: str, body: ProductPatch, ctx: AppContext = Depends(get_ctx)) -> ProductOut:
    if ctx.products.by_sku(sku) is None:
        raise NotFoundError("품목을 찾을 수 없어요.")
    changes = body.model_dump(exclude_unset=True)
    if changes:
        ctx.products.update((sku,), changes)
        ctx.logs.write("품목 수정", sku, ", ".join(changes))
    out = ctx.products.by_sku(sku)
    assert out is not None
    return out
