from __future__ import annotations

from ..core.repository import Repository
from ..core.sheet_schema import MARKET_MAP
from ..core.timeutil import now


class MarketMapRepo(Repository[dict]):
    spec = MARKET_MAP

    def lookup(self) -> dict[tuple[str, str], tuple[str, int]]:
        return {
            (d["source"], d["external_name"]): (d.get("sku") or "", d.get("multiplier") or 1)
            for d in self.rows()
            if d.get("source") and d.get("external_name")
        }

    def upsert(self, source: str, external_name: str, sku: str, multiplier: int) -> None:
        existing = self.get(source, external_name, fresh=True)
        data = {"sku": sku, "multiplier": max(1, multiplier), "updated_at": now()}
        if existing:
            self.update((source, external_name), data)
        else:
            self.insert({"source": source, "external_name": external_name, **data})
