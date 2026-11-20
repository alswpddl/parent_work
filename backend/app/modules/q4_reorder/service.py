"""단골 발주 주기 리마인드.

거래처마다 '주문한 날' 사이 간격의 평균을 구해,
마지막 주문 후 (평균 간격 × 리마인드 기준 배수) 일이 지나도 주문이 없으면 알려준다.
- 주문 횟수가 '리마인드 최소 주문 횟수'보다 적으면 계산하지 않는다 (패턴이 없으니까)
- [나중에] 를 누르면 거래처 탭 '리마인드보류' 날짜까지 목록에서 숨긴다
- 계산 결과(최근주문일·평균주문간격)는 거래처 탭에도 적어 둔다
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean
from typing import Any

from pydantic import BaseModel, Field

from ...core.briefing import BriefingSection
from ...core.errors import NotFoundError
from ...core.timeutil import fmt_date_ko, today


class ReorderStat(BaseModel):
    customer_id: str
    customer_name: str
    phone: str
    order_count: int
    last_order_date: date | None
    avg_interval_days: float | None
    days_since: int | None
    expected_date: date | None
    overdue_days: int  # 기준보다 며칠 넘었나 (음수면 아직 여유)
    due: bool  # 알려줄 대상인가
    snoozed_until: date | None = None
    last_items: str = ""


class SnoozeIn(BaseModel):
    days: int = Field(default=7, ge=1, le=90)


class ReorderService:
    def __init__(self, ctx: Any):
        self.ctx = ctx

    def stats(self, day: date | None = None) -> list[ReorderStat]:
        day = day or today()
        st = self.ctx.settings.load()
        by_cust: dict[str, list] = {}
        for o in self.ctx.orders.query():  # 취소 제외
            if o.customer_id and o.created_at:
                by_cust.setdefault(o.customer_id, []).append(o)
        out: list[ReorderStat] = []
        for c in self.ctx.customers.list():
            if c.type != "B2B":
                continue
            orders = sorted(by_cust.get(c.customer_id, []), key=lambda o: o.created_at)
            dates = sorted({o.created_at.date() for o in orders})
            avg = round(mean((b - a).days for a, b in zip(dates, dates[1:])), 1) if len(dates) >= 2 else None
            last = dates[-1] if dates else None
            since = (day - last).days if last else None
            expected = last + timedelta(days=round(avg)) if (last and avg) else None
            limit = avg * st.reorder_factor if avg else None
            overdue = int(since - limit) if (since is not None and limit is not None) else 0
            snoozed = c.reorder_snooze_until if (c.reorder_snooze_until and c.reorder_snooze_until >= day) else None
            due = bool(len(dates) >= st.reorder_min_orders and limit is not None and since is not None and since > limit and not snoozed)
            last_items = ", ".join(f"{l.product_name} {l.qty}" for l in orders[-1].lines) if orders else ""
            out.append(
                ReorderStat(
                    customer_id=c.customer_id, customer_name=c.name, phone=c.phone, order_count=len(dates),
                    last_order_date=last, avg_interval_days=avg, days_since=since, expected_date=expected,
                    overdue_days=overdue, due=due, snoozed_until=snoozed, last_items=last_items,
                )
            )
        out.sort(key=lambda s: (not s.due, -s.overdue_days, s.customer_name))
        return out

    def reminders(self, day: date | None = None) -> list[ReorderStat]:
        return [s for s in self.stats(day) if s.due]

    def sync_to_sheet(self, stats: list[ReorderStat] | None = None) -> int:
        """거래처 탭의 최근주문일·평균주문간격을 갱신 (바뀐 거래처만, 한 번에)."""
        stats = stats if stats is not None else self.stats()
        current = {c.customer_id: c for c in self.ctx.customers.list(include_inactive=True)}
        updates = []
        for s in stats:
            c = current.get(s.customer_id)
            if c and (c.last_order_date != s.last_order_date or c.avg_interval_days != s.avg_interval_days):
                updates.append(((s.customer_id,), {"last_order_date": s.last_order_date, "avg_interval_days": s.avg_interval_days}))
        self.ctx.customers.update_many(updates)
        return len(updates)

    def snooze(self, customer_id: str, body: SnoozeIn) -> ReorderStat:
        if not self.ctx.customers.by_id(customer_id):
            raise NotFoundError("거래처를 찾을 수 없어요.")
        until = today() + timedelta(days=body.days)
        self.ctx.customers.update((customer_id,), {"reorder_snooze_until": until})
        return next(s for s in self.stats() if s.customer_id == customer_id)

    def job(self) -> dict:
        stats = self.stats()
        return {"updated": self.sync_to_sheet(stats), "due": sum(1 for s in stats if s.due)}

    def briefing_section(self, ctx: Any, day: date) -> BriefingSection | None:
        due = self.reminders(day)
        if not due:
            return None
        lines = [
            f"📞 {s.customer_name}: 마지막 {fmt_date_ko(s.last_order_date)} · 보통 {s.avg_interval_days:g}일마다"
            for s in due[:5]
        ]
        if len(due) > 5:
            lines.append(f"외 {len(due) - 5}곳")
        return BriefingSection(title="주문할 때 된 거래처", lines=lines, priority=30)
