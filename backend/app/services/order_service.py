"""주문 도메인 서비스 — 생성·수정·출고·취소와 이벤트 발행을 한곳에서 처리한다.

라우터(1분기)와 셀프주문(2분기)·오픈마켓 수집(3분기)이 모두 이 서비스를 통해 주문을 만든다.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..core.errors import NotFoundError, ValidationFailed
from ..core.events import EventBus
from ..core.ids import next_order_id
from ..core.timeutil import now, today
from ..repositories.customers import CustomerRepo
from ..repositories.logs import LogRepo
from ..repositories.orders import OrderRepo, to_order_out
from ..repositories.products import ProductRepo
from ..repositories.settings import SettingsRepo
from ..schemas.common import OPEN_STATUSES
from ..schemas.customer import CustomerOut
from ..schemas.order import (
    DraftCustomer,
    DraftItem,
    OrderCreate,
    OrderDraft,
    OrderItemIn,
    OrderOut,
    OrderPatch,
    ProductionLine,
    ProductionSummary,
)
from ..schemas.product import ProductOut
from ..schemas.settings import AppSettings
from .matching import match_customer, match_product
from .shipping_rule import box_count, decide_method, line_kg, pallet_count

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 파서 결과 (AI / 규칙 공통)
# ---------------------------------------------------------------------------
@dataclass
class ParsedItem:
    raw_name: str
    qty: int
    spec: str = ""
    sku: str | None = None


@dataclass
class ParsedOrder:
    customer_id: str | None = None
    customer_name: str = ""
    items: list[ParsedItem] = field(default_factory=list)
    address: str = ""
    phone: str = ""
    due_date: date | None = None
    note: str = ""


class OrderService:
    def __init__(
        self,
        *,
        orders: OrderRepo,
        customers: CustomerRepo,
        products: ProductRepo,
        settings: SettingsRepo,
        logs: LogRepo,
        bus: EventBus,
    ):
        self.orders = orders
        self.customers = customers
        self.products = products
        self.settings = settings
        self.logs = logs
        self.bus = bus
        self._id_lock = threading.Lock()

    # ================================================================ 초안
    def build_draft(self, parsed: ParsedOrder, *, parser: str, warnings: list[str], raw_text: str) -> OrderDraft:
        st = self.settings.load()
        customers = self.customers.list()
        products = self.products.list()
        pmap = {p.sku: p for p in products}
        warnings = list(warnings)

        # --- 거래처
        cust: CustomerOut | None = None
        dc = DraftCustomer(name=parsed.customer_name)
        if parsed.customer_id:
            cust = next((c for c in customers if c.customer_id == parsed.customer_id), None)
        if cust is None and parsed.customer_name:
            cust, cands = match_customer(parsed.customer_name, customers)
            dc.candidates = cands
        if cust is not None:
            dc = DraftCustomer(customer_id=cust.customer_id, name=cust.name, matched=True, candidates=dc.candidates)
        elif not parsed.customer_name:
            warnings.append("거래처를 찾지 못했어요. 목록에서 골라 주세요.")
        else:
            warnings.append(f"'{parsed.customer_name}' 와(과) 같은 거래처가 등록돼 있지 않아요. 고르거나 새로 등록해 주세요.")

        # --- 품목
        items: list[DraftItem] = []
        for it in parsed.items:
            p = pmap.get(it.sku) if it.sku else None
            cands = []
            if p is None:
                p, cands = match_product(it.raw_name, products, it.spec)
            qty = max(0, int(it.qty))
            di = DraftItem(
                sku=p.sku if p else None,
                raw_name=it.raw_name,
                product_name=p.display_name if p else "",
                qty=qty,
                unit_kg=p.unit_kg if p else 0,
                line_kg=line_kg(qty, p),
                matched=p is not None,
                candidates=cands,
            )
            items.append(di)
            if p is None:
                warnings.append(f"'{it.raw_name}' 품목을 확인해 주세요.")
            elif p.unit_kg <= 0:
                warnings.append(f"'{p.display_name}' 의 개당중량이 비어 있어 무게 계산이 0kg 으로 돼요.")
            if qty == 0:
                warnings.append(f"'{it.raw_name}' 수량을 확인해 주세요.")
        if not items:
            warnings.append("품목을 찾지 못했어요. 직접 추가해 주세요.")

        order_kg = round(sum(i.line_kg for i in items), 3)
        method, by = decide_method(order_kg, st, customer_default=cust.default_method if cust else None)

        return OrderDraft(
            parser=parser,
            customer=dc,
            recipient=(cust.contact_name or cust.name) if cust else parsed.customer_name,
            phone=parsed.phone or (cust.phone if cust else ""),
            address=parsed.address or (cust.address if cust else ""),
            zipcode=cust.zipcode if cust and not parsed.address else "",
            due_date=parsed.due_date,
            note=parsed.note,
            items=items,
            order_kg=order_kg,
            ship_method=method,  # type: ignore[arg-type]
            method_by=by,  # type: ignore[arg-type]
            pallets=pallet_count(order_kg, st) if method == "화물" else 0,
            threshold_kg=st.threshold_kg,
            warnings=_dedupe(warnings),
            raw_text=raw_text,
        )

    # ================================================================ 조회
    def _out(self, lines: list[dict[str, Any]], st: AppSettings, pmap: dict[str, ProductOut]) -> OrderOut:
        base = to_order_out(lines)
        boxes = box_count((l.qty, pmap.get(l.sku)) for l in base.lines)
        base.boxes = boxes
        base.pallets = pallet_count(base.order_kg, st)
        return base

    def get(self, order_id: str, fresh: bool = False) -> OrderOut:
        lines = self.orders.lines_of(order_id, fresh=fresh)
        if not lines:
            raise NotFoundError("주문을 찾을 수 없어요.")
        return self._out(lines, self.settings.load(), self.products.map())

    def query(
        self,
        *,
        statuses: list[str] | None = None,
        method: str | None = None,
        due_from: date | None = None,
        due_to: date | None = None,
        customer_id: str | None = None,
        include_cancelled: bool = False,
    ) -> list[OrderOut]:
        st = self.settings.load()
        pmap = self.products.map()
        out = [self._out(lines, st, pmap) for lines in self.orders.grouped().values()]
        if statuses:
            out = [o for o in out if o.status in statuses]
        elif not include_cancelled:
            out = [o for o in out if o.status != "취소"]
        if method:
            out = [o for o in out if o.ship_method == method]
        if customer_id:
            out = [o for o in out if o.customer_id == customer_id]
        if due_from:
            out = [o for o in out if o.due_date and o.due_date >= due_from]
        if due_to:
            out = [o for o in out if o.due_date is None or o.due_date <= due_to]
        out.sort(key=lambda o: (o.due_date or date.max, o.created_at.isoformat() if o.created_at else ""))
        return out

    def production_summary(self, until: date | None = None) -> ProductionSummary:
        open_orders = self.query(statuses=list(OPEN_STATUSES), due_to=until)
        agg: dict[str, ProductionLine] = {}
        for o in open_orders:
            for l in o.lines:
                key = l.sku or l.product_name
                if key not in agg:
                    agg[key] = ProductionLine(sku=l.sku, product_name=l.product_name, qty=0, kg=0, order_count=0)
                agg[key].qty += l.qty
                agg[key].kg = round(agg[key].kg + l.line_kg, 3)
                agg[key].order_count += 1
        return ProductionSummary(
            until=until,
            lines=sorted(agg.values(), key=lambda x: x.product_name),
            parcel_count=sum(1 for o in open_orders if o.ship_method == "택배"),
            truck_count=sum(1 for o in open_orders if o.ship_method == "화물"),
            order_count=len(open_orders),
        )

    # ================================================================ 생성
    def _resolve_items(self, items: list[OrderItemIn], pmap: dict[str, ProductOut]) -> list[tuple[ProductOut, int]]:
        merged: dict[str, int] = {}
        for it in items:
            if it.sku not in pmap:
                raise ValidationFailed(f"품목코드 '{it.sku}' 를 찾을 수 없어요.")
            merged[it.sku] = merged.get(it.sku, 0) + it.qty
        return [(pmap[s], q) for s, q in merged.items()]

    @staticmethod
    def _line_fields(p: ProductOut, qty: int) -> dict[str, Any]:
        return {
            "sku": p.sku,
            "product_name": p.display_name,
            "qty": qty,
            "line_kg": line_kg(qty, p),
            "unit_price": p.unit_price,
            "amount": qty * p.unit_price if p.unit_price is not None else None,
        }

    def create(self, body: OrderCreate, *, actor: str = "관리자") -> OrderOut:
        st = self.settings.load()
        pmap = self.products.map(include_inactive=False)
        resolved = self._resolve_items(body.items, pmap)

        cust: CustomerOut | None = None
        if body.customer_id:
            cust = self.customers.by_id(body.customer_id)
            if cust is None:
                raise ValidationFailed("고른 거래처를 찾을 수 없어요.")
        customer_name = body.customer_name or (cust.name if cust else "")
        if not customer_name:
            raise ValidationFailed("거래처를 골라 주세요.")

        lines_data = [self._line_fields(p, q) for p, q in resolved]
        order_kg = round(sum(l["line_kg"] for l in lines_data), 3)
        method, by = decide_method(
            order_kg, st, manual=body.ship_method, customer_default=cust.default_method if cust else None
        )
        ts = now()
        header = {
            "created_at": ts,
            "updated_at": ts,
            "source": body.source,
            "customer_id": cust.customer_id if cust else "",
            "customer_name": customer_name,
            "order_kg": order_kg,
            "ship_method": method,
            "method_by": by,
            "recipient": body.recipient or (cust.contact_name or cust.name if cust else customer_name),
            "phone": body.phone or (cust.phone if cust else ""),
            "address": body.address or (cust.address if cust else ""),
            "zipcode": body.zipcode or (cust.zipcode if cust and not body.address else ""),
            "due_date": body.due_date,
            "note": body.note,
            "status": "접수",
            "ext_order_no": body.ext_order_no,
        }

        with self._id_lock:
            order_id = next_order_id(self.orders.all_ids(fresh=True), today())
            rows = []
            for i, ld in enumerate(lines_data, start=1):
                row = {"order_id": order_id, "line_no": i, **header, **ld}
                if i == 1:
                    row["raw_text"] = body.raw_text
                rows.append(row)
            self.orders.insert_many(rows)

        out = self._out(rows, st, pmap)
        self.logs.write("주문 접수", order_id, f"{customer_name} · {len(rows)}품목 · {order_kg}kg · {method}", actor=actor)
        self.bus.publish("order.created", {"order": out})
        return out

    # ================================================================ 수정
    def update(self, order_id: str, patch: OrderPatch, *, actor: str = "관리자") -> OrderOut:
        st = self.settings.load()
        pmap = self.products.map()
        lines = self.orders.lines_of(order_id, fresh=True)
        if not lines:
            raise NotFoundError("주문을 찾을 수 없어요.")
        current = to_order_out(lines)
        changes = patch.model_dump(exclude_unset=True)

        if current.status in ("출고완료", "취소"):
            allowed = {"note"}
            if set(changes) - allowed:
                raise ValidationFailed(
                    "출고 완료·취소된 주문은 특이사항만 고칠 수 있어요. 먼저 '대기로 되돌리기'를 해 주세요."
                )

        header: dict[str, Any] = {}
        for f in ("recipient", "phone", "address", "zipcode", "due_date", "note"):
            if f in changes:
                v = changes[f]
                header[f] = v.strip() if isinstance(v, str) else v

        cust = self.customers.by_id(current.customer_id) if current.customer_id else None
        if "customer_id" in changes:
            if changes["customer_id"]:
                cust = self.customers.by_id(changes["customer_id"])
                if cust is None:
                    raise ValidationFailed("고른 거래처를 찾을 수 없어요.")
                header["customer_id"] = cust.customer_id
                header["customer_name"] = cust.name
            else:
                cust = None
                header["customer_id"] = ""
        if changes.get("customer_name"):
            header["customer_name"] = changes["customer_name"].strip()

        if "status" in changes and changes["status"] is not None:
            if changes["status"] not in OPEN_STATUSES:
                raise ValidationFailed("출고 완료와 취소는 전용 버튼으로 해 주세요.")
            header["status"] = changes["status"]

        # --- 품목 교체
        old_lines = sorted(lines, key=lambda x: x.get("line_no") or 0)
        updates: list[tuple[tuple, dict[str, Any]]] = []
        inserts: list[dict[str, Any]] = []
        deletes: list[tuple] = []
        if patch.items is not None:
            resolved = self._resolve_items(patch.items, pmap)
            new_fields = [self._line_fields(p, q) for p, q in resolved]
            max_no = max((l.get("line_no") or 0) for l in old_lines)
            final_lines: list[dict[str, Any]] = []
            for idx, nf in enumerate(new_fields):
                if idx < len(old_lines):
                    ol = old_lines[idx]
                    updates.append(((order_id, ol["line_no"]), dict(nf)))
                    final_lines.append({**ol, **nf})
                else:
                    max_no += 1
                    base = {k: v for k, v in old_lines[0].items() if k not in ("raw_text",)}
                    row = {**base, "line_no": max_no, **nf}
                    inserts.append(row)
                    final_lines.append(row)
            for ol in old_lines[len(new_fields):]:
                deletes.append((order_id, ol["line_no"]))
        else:
            final_lines = old_lines

        closed = current.status in ("출고완료", "취소")
        if not closed:
            order_kg = round(sum((l.get("line_kg") or 0) for l in final_lines), 3)
            header["order_kg"] = order_kg
            # --- 출고방식 재결정 (수동 지정은 유지, 자동/거래처기본은 무게가 바뀌면 다시 계산)
            if patch.ship_method:
                header["ship_method"], header["method_by"] = patch.ship_method, "수동"
            elif patch.auto_method or current.method_by != "수동":
                m, by = decide_method(order_kg, st, customer_default=cust.default_method if cust else None)
                header["ship_method"], header["method_by"] = m, by

        header["updated_at"] = now()

        # 헤더 값은 모든 라인에 같이 쓴다
        upd_index = {k: ch for k, ch in updates}
        for l in final_lines:
            key = (order_id, l["line_no"])
            if any(key == (order_id, r["line_no"]) for r in inserts):
                continue
            upd_index[key] = {**upd_index.get(key, {}), **header}
        for r in inserts:
            r.update(header)

        self.orders.update_many(list(upd_index.items()))
        self.orders.insert_many(inserts)
        self.orders.delete_many(deletes)

        out = self.get(order_id, fresh=True)
        self.logs.write("주문 수정", order_id, ", ".join(sorted(set(changes) - {"auto_method"})), actor=actor)
        self.bus.publish("order.updated", {"order": out})
        return out

    def set_fields(
        self, order_id: str, fields: dict[str, Any], *, publish: str | None = "order.updated", log_action: str = ""
    ) -> OrderOut:
        """주문의 모든 라인에 같은 값을 쓴다 (송장번호·차량번호·알림발송시각 등).

        publish=None 이면 이벤트를 내지 않는다 (알림 기록처럼 이벤트 구독자가 스스로 쓰는 값).
        """
        self._set_status(order_id, fields)
        out = self.get(order_id, fresh=True)
        if log_action:
            self.logs.write(log_action, order_id, ", ".join(f"{k}={v}" for k, v in fields.items() if v not in (None, "")))
        if publish:
            self.bus.publish(publish, {"order": out})
        return out

    def _set_status(self, order_id: str, fields: dict[str, Any]) -> list[dict[str, Any]]:
        lines = self.orders.lines_of(order_id, fresh=True)
        if not lines:
            raise NotFoundError("주문을 찾을 수 없어요.")
        fields = {**fields, "updated_at": now()}
        self.orders.update_many([((order_id, l["line_no"]), fields) for l in lines])
        return lines

    def ship(self, order_id: str, *, actor: str = "관리자") -> OrderOut:
        cur = self.get(order_id, fresh=True)
        if cur.status == "취소":
            raise ValidationFailed("취소된 주문은 출고할 수 없어요.")
        if cur.status == "출고완료":
            return cur
        self._set_status(order_id, {"status": "출고완료", "shipped_at": now()})
        out = self.get(order_id, fresh=True)
        self.logs.write("출고 완료", order_id, f"{out.customer_name} · {out.ship_method}", actor=actor)
        failures = self.bus.publish("order.shipped", {"order": out})
        if failures:
            self.logs.write("출고 후속처리 오류", order_id, "; ".join(f.error for f in failures), actor="시스템", result="실패")
        return out

    def unship(self, order_id: str, *, actor: str = "관리자") -> OrderOut:
        cur = self.get(order_id, fresh=True)
        if cur.status != "출고완료":
            raise ValidationFailed("출고 완료된 주문만 되돌릴 수 있어요.")
        self._set_status(order_id, {"status": "출고대기", "shipped_at": None})
        out = self.get(order_id, fresh=True)
        self.logs.write("출고 되돌리기", order_id, out.customer_name, actor=actor)
        self.bus.publish("order.unshipped", {"order": out})
        return out

    def cancel(self, order_id: str, *, actor: str = "관리자") -> OrderOut:
        cur = self.get(order_id, fresh=True)
        if cur.status == "취소":
            return cur
        was_shipped = cur.status == "출고완료"
        self._set_status(order_id, {"status": "취소"})
        out = self.get(order_id, fresh=True)
        self.logs.write("주문 취소", order_id, out.customer_name + (" (출고 후 취소)" if was_shipped else ""), actor=actor)
        self.bus.publish("order.cancelled", {"order": out, "was_shipped": was_shipped})
        return out


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
