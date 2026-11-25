"""원부자재 재고.

- 품목 탭의 '용기자재/뚜껑자재/라벨자재/박스자재/저장고품목' 열에 자재코드를 적어 두면
  출고 완료 때 자동으로 차감: 용기·뚜껑·라벨 = 수량만큼, 박스 = 수량 ÷ 박스입수 (올림),
  저장고(젓갈 kg) = 내용량kg × 수량
- 재고는 소수점까지 (저장고 152.5kg 처럼)
- 같은 주문을 두 번 차감하지 않도록 주문장 '재고차감' 칸을 TRUE 로 표시
- 출고 되돌리기·출고 후 취소 → 다시 더해 줌
- 모든 변동은 '_재고이력' 탭에 한 줄씩 남는다
- 안전재고 이하이거나, 최근 30일 사용량 기준 '발주 소요일' 안에 바닥날 것 같으면 경고
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from ...core.briefing import BriefingSection
from ...core.errors import NotFoundError, ValidationFailed
from ...core.ids import next_seq_id
from ...core.repository import Repository
from ...core.sheet_schema import INVENTORY, STOCK_MOVES
from ...core.timeutil import fmt_date_ko, now, today
from ...schemas.order import OrderOut
from ...schemas.product import ProductOut

log = logging.getLogger(__name__)
USAGE_WINDOW_DAYS = 30
CATEGORY_ORDER = ["저장고", "용기", "뚜껑", "라벨", "박스"]


def fmt_qty(v: float) -> str:
    """150.0 → '150', 152.5 → '152.5', 1500 → '1,500'"""
    v = round(float(v), 3)
    return f"{int(v):,}" if v.is_integer() else f"{v:,.3f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------- 모델
class ItemIn(BaseModel):
    item_id: str | None = Field(default=None, max_length=30)
    category: str = "기타"
    name: str = Field(min_length=1, max_length=60)
    unit: str = "개"
    stock: float = Field(default=0, ge=0)
    safety_stock: float = Field(default=0, ge=0)
    reorder_qty: float = Field(default=0, ge=0)
    supplier: str = ""
    supplier_phone: str = ""


class ItemPatch(BaseModel):
    category: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=60)
    unit: str | None = None
    safety_stock: float | None = Field(default=None, ge=0)
    reorder_qty: float | None = Field(default=None, ge=0)
    supplier: str | None = None
    supplier_phone: str | None = None


class ReceiveIn(BaseModel):
    qty: float = Field(gt=0, le=10_000_000)
    memo: str = ""


class AdjustIn(BaseModel):
    stock: float = Field(ge=0, le=10_000_000)
    reason: str = Field(min_length=1, max_length=100)


class StocktakeIn(BaseModel):
    """재고 한꺼번에 입력: {자재코드: 실제로 센 양}. 바뀐 것만 반영된다."""

    counts: dict[str, float] = Field(min_length=1)
    reason: str = Field(default="재고 조사", min_length=1, max_length=100)




class NeedOut(BaseModel):
    """출고 전 주문들이 쓸 자재 vs 지금 재고"""

    item_id: str
    name: str
    category: str
    unit: str
    need: float
    stock: float
    short: float  # 모자라는 양 (0 이면 충분)


class ItemOut(BaseModel):
    item_id: str
    category: str
    name: str
    unit: str
    stock: float
    safety_stock: float
    reorder_qty: float
    supplier: str
    supplier_phone: str
    status: str  # 정상 / 곧부족 / 부족 / 없음
    avg_daily_use: float
    days_left: float | None
    order_by: str | None  # 이 날까지 발주해야 안 끊김
    used_by: list[str]  # 이 자재를 쓰는 품목


class StocktakeOut(BaseModel):
    changed: int
    items: list[ItemOut]


class MoveOut(BaseModel):
    ts: str
    item_id: str
    item_name: str
    change: float
    stock_after: float
    reason: str
    order_id: str


def requirements(order: OrderOut, pmap: dict[str, ProductOut]) -> dict[str, float]:
    """주문 하나가 쓰는 자재: {자재코드: 양}"""
    need: dict[str, float] = {}

    def add(code: str, qty: float) -> None:
        if code and qty:
            need[code] = round(need.get(code, 0) + qty, 3)

    for l in order.lines:
        p = pmap.get(l.sku)
        if not p or l.qty <= 0:
            continue
        add(p.container_item, l.qty)
        add(p.lid_item, l.qty)
        add(p.label_item, l.qty)
        if p.box_item:
            add(p.box_item, math.ceil(l.qty / p.units_per_box) if p.units_per_box else l.qty)
        if p.bulk_item:
            add(p.bulk_item, p.content_kg * l.qty)
    return need


def _material_codes(p: ProductOut) -> set[str]:
    return {p.container_item, p.box_item, p.label_item, p.lid_item, p.bulk_item} - {""}


class InventoryService:
    def __init__(self, ctx: Any):
        self.ctx = ctx
        self.items: Repository[dict] = Repository(ctx.sheets, INVENTORY)
        self.moves: Repository[dict] = Repository(ctx.sheets, STOCK_MOVES)

    # ---------------------------------------------------------------- 조회
    def _usage(self, day: date) -> dict[str, float]:
        since = day - timedelta(days=USAGE_WINDOW_DAYS)
        used: dict[str, float] = {}
        for m in self.moves.rows():
            ts = m.get("ts")
            if not ts or ts.date() < since or (m.get("change") or 0) >= 0:
                continue
            if not str(m.get("reason", "")).startswith("출고"):
                continue
            used[m["item_id"]] = used.get(m["item_id"], 0) - m["change"]
        return {k: v / USAGE_WINDOW_DAYS for k, v in used.items()}

    def list_items(self, day: date | None = None) -> list[ItemOut]:
        day = day or today()
        lead = self.ctx.settings.load().stock_lead_days
        usage = self._usage(day)
        used_by: dict[str, list[str]] = {}
        for p in self.ctx.products.list():
            for code in _material_codes(p):
                used_by.setdefault(code, []).append(p.display_name)
        out = []
        for d in self.items.rows():
            if not d.get("item_id"):
                continue
            stock, safety = d.get("stock") or 0, d.get("safety_stock") or 0
            daily = round(usage.get(d["item_id"], 0.0), 2)
            days_left = round(stock / daily, 1) if daily > 0 else None
            order_by = None
            if days_left is not None:
                order_by_day = day + timedelta(days=max(0, math.floor(days_left - lead)))
                order_by = fmt_date_ko(order_by_day)
            if stock <= 0:
                status = "없음"
            elif safety and stock <= safety:
                status = "부족"
            elif days_left is not None and days_left <= lead + 2:
                status = "곧부족"
            else:
                status = "정상"
            out.append(
                ItemOut(
                    item_id=d["item_id"], category=d.get("category") or "기타", name=d.get("name") or d["item_id"],
                    unit=d.get("unit") or "개", stock=stock, safety_stock=safety, reorder_qty=d.get("reorder_qty") or 0,
                    supplier=d.get("supplier") or "", supplier_phone=d.get("supplier_phone") or "", status=status,
                    avg_daily_use=daily, days_left=days_left, order_by=order_by, used_by=used_by.get(d["item_id"], []),
                )
            )
        rank = {"없음": 0, "부족": 1, "곧부족": 2, "정상": 3}
        cat = {c: i for i, c in enumerate(CATEGORY_ORDER)}
        return sorted(out, key=lambda i: (rank[i.status], cat.get(i.category, 99), i.category, i.name))

    def recent_moves(self, item_id: str | None = None, limit: int = 100) -> list[MoveOut]:
        rows = [m for m in self.moves.rows() if not item_id or m.get("item_id") == item_id]
        rows = [m for _, m in sorted(enumerate(rows), key=lambda x: (x[1].get("ts") or now(), x[0]), reverse=True)]
        return [
            MoveOut(
                ts=m["ts"].strftime("%Y-%m-%d %H:%M") if m.get("ts") else "", item_id=m.get("item_id", ""),
                item_name=m.get("item_name", ""), change=m.get("change") or 0, stock_after=m.get("stock_after") or 0,
                reason=m.get("reason", ""), order_id=m.get("order_id", ""),
            )
            for m in rows[:limit]
        ]

    # ---------------------------------------------------------------- 변경
    def create(self, body: ItemIn) -> ItemOut:
        existing = {str(d.get("item_id") or "") for d in self.items.rows(fresh=True)}
        item_id = (body.item_id or "").strip() or next_seq_id(existing, "M")
        if item_id in existing:
            raise ValidationFailed(f"자재코드 '{item_id}' 가 이미 있어요.")
        data = body.model_dump(exclude={"item_id"})
        self.items.insert({"item_id": item_id, **data, "updated_at": now()})
        if body.stock:
            self._move(item_id, body.name, body.stock, body.stock, "최초 등록", "")
        return self._one(item_id)

    def update(self, item_id: str, body: ItemPatch) -> ItemOut:
        self._require(item_id)
        changes = body.model_dump(exclude_unset=True)
        if changes:
            self.items.update((item_id,), {**changes, "updated_at": now()})
        return self._one(item_id)

    def receive(self, item_id: str, body: ReceiveIn) -> ItemOut:
        self.apply({item_id: body.qty}, reason=f"입고{(' · ' + body.memo) if body.memo else ''}")
        return self._one(item_id)

    def adjust(self, item_id: str, body: AdjustIn) -> ItemOut:
        d = self._require(item_id)
        delta = round(body.stock - (d.get("stock") or 0), 3)
        if delta:
            self.apply({item_id: delta}, reason=f"실사조정 · {body.reason}")
        return self._one(item_id)

    def stocktake(self, body: StocktakeIn) -> StocktakeOut:
        """여러 자재를 한 번에 '실제로 센 양'으로 맞춘다 (시트 쓰기 2번)."""
        current = {d["item_id"]: d for d in self.items.rows(fresh=True) if d.get("item_id")}
        unknown = [k for k in body.counts if k not in current]
        if unknown:
            raise ValidationFailed(f"없는 자재코드예요: {', '.join(unknown)}")
        deltas = {}
        for k, v in body.counts.items():
            if v < 0:
                raise ValidationFailed("재고는 0 이상으로 넣어 주세요.")
            d = round(v - (current[k].get("stock") or 0), 3)
            if d:
                deltas[k] = d
        if deltas:
            self.apply(deltas, reason=f"실사조정 · {body.reason}")
            self.ctx.logs.write("재고 조사", f"{len(deltas)}개", body.reason)
        return StocktakeOut(changed=len(deltas), items=self.list_items())

    def needs(self, until: date | None = None) -> list[NeedOut]:
        """아직 출고 안 한 주문(받는 날 ≤ until, 날짜 미정 포함)에 필요한 자재 vs 지금 재고."""
        pmap = self.ctx.products.map()
        total: dict[str, float] = {}
        for o in self.ctx.orders.query(statuses=["접수", "출고대기"], due_to=until):
            if o.stock_deducted:
                continue
            for k, v in requirements(o, pmap).items():
                total[k] = round(total.get(k, 0) + v, 3)
        items = {i.item_id: i for i in self.list_items()}
        out = []
        for code, need in total.items():
            it = items.get(code)
            stock = it.stock if it else 0
            out.append(NeedOut(
                item_id=code, name=it.name if it else f"{code} (자재 탭에 없음)", category=it.category if it else "기타",
                unit=it.unit if it else "", need=need, stock=stock, short=round(max(0.0, need - stock), 3),
            ))
        cat = {c: i for i, c in enumerate(CATEGORY_ORDER)}
        return sorted(out, key=lambda n: (n.short <= 0, cat.get(n.category, 99), n.name))

    def apply(self, changes: dict[str, float], *, reason: str, order_id: str = "") -> list[str]:
        """재고 더하기/빼기. 없는 자재코드 목록을 돌려준다."""
        with self.ctx.sheets.lock:
            current = {d["item_id"]: d for d in self.items.rows(fresh=True) if d.get("item_id")}
            missing = [k for k in changes if k not in current]
            updates = []
            moves = []
            ts = now()
            for item_id, delta in changes.items():
                if item_id not in current or delta == 0:
                    continue
                d = current[item_id]
                after = round((d.get("stock") or 0) + delta, 3)  # 음수 허용: 실제보다 적게 적혀 있었다는 신호
                updates.append(((item_id,), {"stock": after, "updated_at": ts}))
                moves.append({
                    "ts": ts, "item_id": item_id, "item_name": d.get("name", ""), "change": delta,
                    "stock_after": after, "reason": reason, "order_id": order_id,
                })
            self.items.update_many(updates)
            self.moves.insert_many(moves)
        if missing:
            self.ctx.logs.write("자재코드 없음", ",".join(missing), f"{reason} {order_id}", actor="시스템", result="확인필요")
        return missing

    def _move(self, item_id: str, name: str, change: float, after: float, reason: str, order_id: str) -> None:
        self.moves.insert({"ts": now(), "item_id": item_id, "item_name": name, "change": change,
                           "stock_after": after, "reason": reason, "order_id": order_id})

    def _require(self, item_id: str) -> dict:
        d = self.items.get(item_id, fresh=True)
        if not d:
            raise NotFoundError("자재를 찾을 수 없어요.")
        return d

    def _one(self, item_id: str) -> ItemOut:
        for i in self.list_items():
            if i.item_id == item_id:
                return i
        raise NotFoundError("자재를 찾을 수 없어요.")

    # ---------------------------------------------------------------- 주문 연동
    def deduct(self, order: OrderOut) -> dict[str, float]:
        if order.stock_deducted:
            return {}
        need = requirements(order, self.ctx.products.map())
        if not need:
            return {}
        self.apply({k: -v for k, v in need.items()}, reason="출고 차감", order_id=order.order_id)
        self.ctx.orders.set_fields(order.order_id, {"stock_deducted": True}, publish=None)
        return need

    def restore(self, order: OrderOut, reason: str) -> dict[str, float]:
        if not order.stock_deducted:
            return {}
        need = requirements(order, self.ctx.products.map())
        if need:
            self.apply(need, reason=reason, order_id=order.order_id)
        self.ctx.orders.set_fields(order.order_id, {"stock_deducted": False}, publish=None)
        return need

    def on_shipped(self, payload: dict) -> None:
        if self.deduct(payload["order"]):
            self.check_and_alert()

    def on_unshipped(self, payload: dict) -> None:
        self.restore(payload["order"], "출고취소 복원")

    def on_cancelled(self, payload: dict) -> None:
        if payload.get("was_shipped"):
            self.restore(payload["order"], "주문취소 복원")

    # ---------------------------------------------------------------- 경고
    def low_items(self) -> list[ItemOut]:
        return [i for i in self.list_items() if i.status in ("없음", "부족", "곧부족")]

    def check_and_alert(self, force: bool = False) -> dict:
        low = self.low_items()
        if not low:
            return {"low": 0, "alerted": 0}
        if not force and not self.ctx.settings.load().stock_alert_enabled:
            return {"low": len(low), "alerted": 0, "reason": "경고 꺼짐"}
        t = today()
        raw = {d["item_id"]: d for d in self.items.rows(fresh=True) if d.get("item_id")}
        targets = [i for i in low if force or not raw[i.item_id].get("last_alert_at") or raw[i.item_id]["last_alert_at"].date() < t]
        if not targets:
            return {"low": len(low), "alerted": 0, "reason": "오늘 이미 알림"}
        lines = ["⚠️ 자재 발주가 필요해요"] + [self._line(i) for i in targets]
        if self.ctx.notifier.send("재고경고", "\n".join(lines), path="/inventory", button="재고 보기"):
            self.items.update_many([((i.item_id,), {"last_alert_at": now()}) for i in targets])
            return {"low": len(low), "alerted": len(targets)}
        return {"low": len(low), "alerted": 0, "reason": "카카오 발송 실패"}

    @staticmethod
    def _line(i: ItemOut) -> str:
        s = f"· {i.name} {fmt_qty(i.stock)}{i.unit} (안전 {fmt_qty(i.safety_stock)})"
        if i.days_left is not None:
            s += f" · 약 {i.days_left:g}일분"
        if i.reorder_qty:
            s += f" → {fmt_qty(i.reorder_qty)}{i.unit} {'보충' if i.category == '저장고' else '발주'}"
        if i.supplier:
            s += f" [{i.supplier}]"
        return s

    def briefing_section(self, ctx: Any, day: date) -> BriefingSection | None:
        low = self.low_items()
        if not low:
            return None
        return BriefingSection(title="자재 재고", lines=[self._line(i) for i in low[:6]], priority=20)
