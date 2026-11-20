from __future__ import annotations

from ..core.ids import next_seq_id
from ..core.repository import Repository
from ..core.sheet_schema import PRODUCTS
from ..schemas.product import ProductOut


class ProductRepo(Repository[ProductOut]):
    spec = PRODUCTS

    def list(self, include_inactive: bool = False, fresh: bool = False) -> list[ProductOut]:
        out = [ProductOut.from_row(d) for d in self.rows(fresh) if d.get("sku")]
        if not include_inactive:
            out = [p for p in out if p.active]
        return sorted(out, key=lambda p: (p.name, p.spec))

    def by_sku(self, sku: str) -> ProductOut | None:
        d = self.get(sku)
        return ProductOut.from_row(d) if d else None

    def map(self, include_inactive: bool = True) -> dict[str, ProductOut]:
        return {p.sku: p for p in self.list(include_inactive=include_inactive)}

    def new_sku(self) -> str:
        return next_seq_id((d.get("sku") or "" for d in self.rows(fresh=True)), "P")
