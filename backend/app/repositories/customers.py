from __future__ import annotations

from ..core.ids import next_seq_id
from ..core.repository import Repository
from ..core.sheet_schema import CUSTOMERS
from ..schemas.customer import CustomerOut


class CustomerRepo(Repository[CustomerOut]):
    spec = CUSTOMERS

    def list(self, include_inactive: bool = False, fresh: bool = False) -> list[CustomerOut]:
        out = [CustomerOut.from_row(d) for d in self.rows(fresh) if d.get("customer_id")]
        if not include_inactive:
            out = [c for c in out if c.active]
        return sorted(out, key=lambda c: c.name)

    def by_id(self, customer_id: str) -> CustomerOut | None:
        d = self.get(customer_id)
        return CustomerOut.from_row(d) if d else None

    def new_id(self) -> str:
        return next_seq_id((d.get("customer_id") or "" for d in self.rows(fresh=True)), "C")
