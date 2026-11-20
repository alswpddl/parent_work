"""스마트스토어·쿠팡 주문 엑셀을 주문장 형식으로 바꿔 넣는다.

1) 업로드 → 마켓 자동 판별 → 주문번호별로 묶음
2) 각 상품명(+옵션)을 우리 품목으로 연결: '_상품매핑' 탭에 저장된 값 → 없으면 이름 유사도로 추천
3) 미리보기에서 품목·수량배수를 고르고 [등록] → 주문 생성 (경로=스마트스토어/쿠팡, 외부주문번호로 중복 방지)
   '기억하기'를 체크하면 _상품매핑 에 저장돼 다음부터는 자동
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...core.errors import ValidationFailed
from ...core.uploads import PreviewStore, cell_text, find_table, pick, read_rows
from ...repositories.market_map import MarketMapRepo
from ...schemas.order import Candidate, OrderCreate, OrderItemIn
from ...services.matching import match_product
from .adapters import ADAPTERS, Adapter, detection_hints


class MarketLine(BaseModel):
    external_name: str
    qty: int
    sku: str | None = None
    multiplier: int = 1
    mapped: bool = False  # _상품매핑 에서 찾음
    candidates: list[Candidate] = []


class MarketOrder(BaseModel):
    ext_order_no: str
    recipient: str
    phone: str
    address: str
    zipcode: str
    message: str
    lines: list[MarketLine]
    status: str  # 등록가능 / 확인필요 / 이미등록


class MarketPreview(BaseModel):
    preview_id: str
    source: str
    adapter: str
    orders: list[MarketOrder]
    unmapped_names: list[str]
    ready: int
    duplicates: int


class MappingIn(BaseModel):
    sku: str
    multiplier: int = Field(default=1, ge=1, le=1000)
    remember: bool = True


class MarketConfirmIn(BaseModel):
    mappings: dict[str, MappingIn] = Field(default_factory=dict, description="{외부상품명: 매핑}")
    skip_orders: list[str] = Field(default_factory=list)


class MarketResult(BaseModel):
    created: int
    skipped: int
    order_ids: list[str]
    errors: list[str]


class MarketplaceService:
    def __init__(self, ctx: Any):
        self.ctx = ctx
        self.maps = MarketMapRepo(ctx.sheets)
        self.previews = PreviewStore()

    def _detect(self, rows: list[list[Any]], source: str) -> tuple[Adapter, Any]:
        if source in ADAPTERS:
            return ADAPTERS[source], find_table(rows, detection_hints(ADAPTERS[source]), min_hits=3)
        best = None
        for a in ADAPTERS.values():
            try:
                t = find_table(rows, detection_hints(a), min_hits=3)
            except ValidationFailed:
                continue
            score = sum(1 for k in ("recipient", "phone", "product", "qty") if pick(t.rows[0], a.fields[k]) is not None) if t.rows else 0
            if best is None or score > best[0]:
                best = (score, a, t)
        if best is None:
            raise ValidationFailed("스마트스토어/쿠팡 주문 엑셀 형식을 알아보지 못했어요. 판매자센터에서 받은 원본을 올려 주세요.")
        return best[1], best[2]

    def preview(self, filename: str, data: bytes, source: str = "auto") -> MarketPreview:
        adapter, table = self._detect(read_rows(filename, data), source)
        f = adapter.fields
        mapping = self.maps.lookup()
        products = self.ctx.products.list()
        existing_ext = {o.ext_order_no for o in self.ctx.orders.query(include_cancelled=True) if o.ext_order_no}

        grouped: dict[str, MarketOrder] = {}
        for r in table.rows:
            order_no = cell_text(pick(r, f["order_no"]))
            product = cell_text(pick(r, f["product"]))
            if not order_no or not product:
                continue
            option = cell_text(pick(r, f["option"]))
            ext_name = f"{product} / {option}" if option else product
            try:
                qty = int(float(cell_text(pick(r, f["qty"])) or "1"))
            except ValueError:
                qty = 1
            key = f"{adapter.code}:{order_no}"
            if key not in grouped:
                addr = cell_text(pick(r, f["address"]))
                addr2 = cell_text(pick(r, f["address2"])) if f["address2"] else ""
                grouped[key] = MarketOrder(
                    ext_order_no=key,
                    recipient=cell_text(pick(r, f["recipient"])),
                    phone=cell_text(pick(r, f["phone"])),
                    address=f"{addr} {addr2}".strip() if addr2 and addr2 not in addr else addr,
                    zipcode=cell_text(pick(r, f["zipcode"])).zfill(5) if pick(r, f["zipcode"]) else "",
                    message=cell_text(pick(r, f["message"])),
                    lines=[],
                    status="등록가능",
                )
            line = MarketLine(external_name=ext_name, qty=max(1, qty))
            hit = mapping.get((adapter.source, ext_name))
            if hit and hit[0]:
                line.sku, line.multiplier, line.mapped = hit[0], hit[1], True
            else:
                best, cands = match_product(ext_name, products)
                line.candidates = cands
                line.sku = best.sku if best else None
            grouped[key].lines.append(line)

        unmapped: set[str] = set()
        for o in grouped.values():
            if o.ext_order_no in existing_ext:
                o.status = "이미등록"
            elif any(not l.mapped for l in o.lines):
                o.status = "확인필요"
                unmapped.update(l.external_name for l in o.lines if not l.mapped)

        orders = list(grouped.values())
        preview = MarketPreview(
            preview_id="",
            source=adapter.source,
            adapter=adapter.code,
            orders=orders,
            unmapped_names=sorted(unmapped),
            ready=sum(1 for o in orders if o.status != "이미등록"),
            duplicates=sum(1 for o in orders if o.status == "이미등록"),
        )
        preview.preview_id = self.previews.put(preview)
        return preview

    def confirm(self, preview_id: str, body: MarketConfirmIn) -> MarketResult:
        preview: MarketPreview = self.previews.get(preview_id)
        pmap = self.ctx.products.map(include_inactive=False)
        for name, m in body.mappings.items():
            if m.sku not in pmap:
                raise ValidationFailed(f"'{name}' 에 고른 품목코드 {m.sku} 가 없어요.")
            if m.remember:
                self.maps.upsert(preview.source, name, m.sku, m.multiplier)

        skip = set(body.skip_orders)
        created, skipped, ids, errors = 0, 0, [], []
        for o in preview.orders:
            if o.status == "이미등록" or o.ext_order_no in skip:
                skipped += 1
                continue
            items: dict[str, int] = {}
            missing = []
            for l in o.lines:
                picked = body.mappings.get(l.external_name)
                sku, mult = (picked.sku, picked.multiplier) if picked else (l.sku, l.multiplier)
                if not sku or sku not in pmap:
                    missing.append(l.external_name)
                    continue
                items[sku] = items.get(sku, 0) + l.qty * mult
            if missing:
                errors.append(f"{o.ext_order_no} ({o.recipient}): 품목을 고르지 않음 → {', '.join(missing)}")
                skipped += 1
                continue
            try:
                out = self.ctx.orders.create(
                    OrderCreate(
                        customer_name=o.recipient or preview.source,
                        recipient=o.recipient,
                        phone=o.phone,
                        address=o.address,
                        zipcode=o.zipcode,
                        note=o.message,
                        items=[OrderItemIn(sku=s, qty=q) for s, q in items.items()],
                        source=preview.source,  # type: ignore[arg-type]
                        ext_order_no=o.ext_order_no,
                    ),
                    actor=preview.source,
                )
                created += 1
                ids.append(out.order_id)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{o.ext_order_no}: {getattr(e, 'message', str(e))}")
        self.previews.pop(preview_id)
        self.ctx.logs.write("오픈마켓 주문 등록", preview.source, f"{created}건 등록, {skipped}건 건너뜀")
        return MarketResult(created=created, skipped=skipped, order_ids=ids, errors=errors)

    def mappings(self) -> list[dict]:
        return sorted(self.maps.rows(), key=lambda d: (d.get("source", ""), d.get("external_name", "")))

    def delete_mapping(self, source: str, external_name: str) -> None:
        self.maps.delete_many([(source, external_name)])
