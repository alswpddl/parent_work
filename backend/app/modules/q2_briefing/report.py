"""아침 브리핑 만들기·보내기.

섹션은 ctx.briefing 레지스트리에서 모은다. 이 모듈은 '생산·출고' 섹션을 등록하고,
4분기 모듈들이 '재고 부족', '주문할 때 된 거래처', '미수금' 섹션을 덧붙인다.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel

from ...core.briefing import BriefingSection
from ...core.timeutil import WEEKDAYS_KO, now, today
from ...schemas.common import OPEN_STATUSES


class SectionOut(BaseModel):
    title: str
    lines: list[str]


class BriefingOut(BaseModel):
    day: date
    text: str
    sections: list[SectionOut]
    kakao_connected: bool
    enabled: bool


def core_section(ctx: Any, day: date) -> BriefingSection | None:
    open_orders = ctx.orders.query(statuses=list(OPEN_STATUSES))
    tomorrow = day + timedelta(days=1)
    overdue = [o for o in open_orders if o.due_date and o.due_date < day]
    due_today = [o for o in open_orders if o.due_date == day]
    due_tomorrow = [o for o in open_orders if o.due_date == tomorrow]
    parcel = sum(1 for o in open_orders if o.ship_method == "택배")
    truck = sum(1 for o in open_orders if o.ship_method == "화물")

    lines = [f"📦 택배 {parcel}건 · 🚚 화물 {truck}건 출고 대기"]
    if overdue:
        lines.append(f"⏰ 납기 지난 주문 {len(overdue)}건: " + ", ".join(o.customer_name for o in overdue[:5]))
    lines.append(f"오늘 납기 {len(due_today)}건 · 내일 납기 {len(due_tomorrow)}건")

    summary = ctx.orders.production_summary(until=tomorrow)
    if summary.lines:
        lines.append("🔨 내일까지 만들 물량")
        for l in summary.lines:
            lines.append(f" · {l.product_name} {l.qty:,}개 ({l.order_count}건)")
    elif not open_orders:
        lines.append("대기 중인 주문이 없어요.")
    return BriefingSection(title="생산·출고", lines=lines, priority=10)


class BriefingService:
    def __init__(self, ctx: Any):
        self.ctx = ctx

    def build(self, day: date | None = None) -> tuple[str, list[BriefingSection]]:
        day = day or today()
        sections = self.ctx.briefing.collect(self.ctx, day)
        head = f"🏭 {day.month}/{day.day}({WEEKDAYS_KO[day.weekday()]}) 아침 브리핑"
        parts = [head]
        for s in sections:
            parts.append("")
            if s.title != "생산·출고":
                parts.append(f"[{s.title}]")
            parts.extend(s.lines)
        return "\n".join(parts), sections

    def preview(self, day: date | None = None) -> BriefingOut:
        day = day or today()
        text, sections = self.build(day)
        return BriefingOut(
            day=day,
            text=text,
            sections=[SectionOut(title=s.title, lines=s.lines) for s in sections],
            kakao_connected=bool(self.ctx.kakao.configured and self.ctx.kakao.status()["connected"]),
            enabled=self.ctx.settings.load().briefing_enabled,
        )

    def send(self, *, force: bool = False) -> dict:
        if not force and not self.ctx.settings.load().briefing_enabled:
            return {"sent": False, "reason": "브리핑 꺼짐 (_설정)"}
        text, _ = self.build()
        ok = self.ctx.notifier.send("아침브리핑", text, path="/", button="오늘 할 일 보기")
        return {"sent": ok, "at": now().isoformat(), "length": len(text)}
