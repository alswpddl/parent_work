"""숙성 저장소 지도 — 건물(도형) 안에 저장소를 줄·칸으로 놓고, 담근 날로 숙성 단계를 계산한다.

상태 (색): 숙성 끝(ready) · 숙성 중(aging) · 비어 있음(empty)
  - 비어 있음: 현재kg 가 0 이거나 비었음
  - 숙성 끝: 담근 날 + 숙성 기간(_설정 aging_months, 기본 24개월) 이 오늘 이전
  - 숙성 중: 그 밖 (담근 날을 모르면 '숙성 중 · 담근 날 미입력')
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from ...core.errors import NotFoundError, ValidationFailed
from ...core.repository import Repository
from ...core.sheet_schema import TANKS
from ...core.timeutil import now, today

Status = Literal["ready", "aging", "empty"]


def parse_filled(text: str | None) -> date | None:
    """'2024-06', '2024.6', '24.6', '2024-06-15', '2024년 6월' → 날짜 (월만 있으면 15일로)"""
    s = (text or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{2}|\d{4})\s*[-./년]\s*(\d{1,2})(?:\s*[-./월]\s*(\d{1,2}))?", s)
    if not m:
        return None
    y = int(m.group(1))
    y = y + 2000 if y < 100 else y
    mo = int(m.group(2))
    d = int(m.group(3)) if m.group(3) else 15
    try:
        return date(y, mo, min(d, 28) if m.group(3) is None else d)
    except ValueError:
        return None


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, min(d.day, 28))


def months_between(a: date, b: date) -> int:
    """a → b 까지 남은 개월 (올림)"""
    n = (b.year - a.year) * 12 + (b.month - a.month)
    if b.day > a.day:
        n += 1
    return max(n, 0)


class TankOut(BaseModel):
    tank_id: str
    building: str
    no: int
    row: int
    col: int
    capacity_kg: float
    current_kg: float
    product: str
    filled_on: str
    memo: str
    status: Status
    ready_on: date | None  # 출하 가능일 (담근 날 모르면 None)
    months_left: int | None  # 숙성 끝까지 남은 개월 (끝났으면 0)
    progress: int  # 숙성 진행률 0~100


class BuildingOut(BaseModel):
    name: str
    rows: int
    cols: int
    total_kg: float
    tanks: list[TankOut]


class TankSummary(BaseModel):
    ready_count: int
    ready_kg: float
    aging_count: int
    aging_kg: float
    empty_count: int
    in_3m_kg: float  # 3개월 안에 숙성 끝 (지금 끝난 것 포함)
    in_6m_kg: float
    in_12m_kg: float


class TankMapOut(BaseModel):
    aging_months: int
    summary: TankSummary
    buildings: list[BuildingOut]


class BuildingIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    count: int = Field(ge=1, le=40, description="저장소 개수")
    per_row: int = Field(default=5, ge=1, le=20, description="한 줄에 몇 개")
    capacity_kg: float = Field(default=0, ge=0)
    product: str = Field(default="멸치액젓", max_length=40)


class TankPatch(BaseModel):
    current_kg: float | None = Field(default=None, ge=0)
    capacity_kg: float | None = Field(default=None, ge=0)
    filled_on: str | None = Field(default=None, max_length=20)
    product: str | None = Field(default=None, max_length=40)
    memo: str | None = Field(default=None, max_length=200)
    row: int | None = Field(default=None, ge=1, le=40)
    col: int | None = Field(default=None, ge=1, le=40)


def _natural(s: str) -> list[Any]:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


class AgingService:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.repo: Repository[dict] = Repository(ctx.sheets, TANKS)

    @property
    def months(self) -> int:
        return int(getattr(self.ctx.settings.load(), "aging_months", 24) or 24)

    # ------------------------------------------------------------------ 읽기
    def _tank(self, d: dict[str, Any], day: date, months: int) -> TankOut:
        kg = float(d.get("current_kg") or 0)
        filled = parse_filled(d.get("filled_on"))
        ready_on = add_months(filled, months) if filled else None
        if kg <= 0:
            status: Status = "empty"
        elif ready_on and ready_on <= day:
            status = "ready"
        else:
            status = "aging"
        left = months_between(day, ready_on) if ready_on and status != "empty" else None
        if filled and ready_on and status != "empty":
            span = max((ready_on - filled).days, 1)
            progress = max(0, min(100, round((day - filled).days / span * 100)))
        else:
            progress = 0
        return TankOut(
            tank_id=str(d.get("tank_id") or ""), building=str(d.get("building") or "미지정"),
            no=int(d.get("no") or 0), row=int(d.get("row") or 1), col=int(d.get("col") or 1),
            capacity_kg=float(d.get("capacity_kg") or 0), current_kg=kg, product=str(d.get("product") or ""),
            filled_on=str(d.get("filled_on") or ""), memo=str(d.get("memo") or ""),
            status=status, ready_on=ready_on if status != "empty" else None, months_left=left, progress=progress,
        )

    def tanks(self, fresh: bool = False) -> list[TankOut]:
        day, months = today(), self.months
        return [self._tank(r.data, day, months) for r in self.repo.all(fresh) if r.data.get("tank_id")]

    def map(self) -> TankMapOut:
        tanks = self.tanks(fresh=True)
        by_b: dict[str, list[TankOut]] = {}
        for t in tanks:
            by_b.setdefault(t.building, []).append(t)
        buildings = []
        for name in sorted(by_b, key=_natural):
            ts = sorted(by_b[name], key=lambda t: (t.row, t.col, t.no))
            buildings.append(BuildingOut(
                name=name, rows=max(t.row for t in ts), cols=max(t.col for t in ts),
                total_kg=round(sum(t.current_kg for t in ts), 1), tanks=ts,
            ))

        def within(m: int) -> float:
            return round(sum(t.current_kg for t in tanks if t.status != "empty" and t.months_left is not None and t.months_left <= m), 1)

        ready = [t for t in tanks if t.status == "ready"]
        aging = [t for t in tanks if t.status == "aging"]
        summary = TankSummary(
            ready_count=len(ready), ready_kg=round(sum(t.current_kg for t in ready), 1),
            aging_count=len(aging), aging_kg=round(sum(t.current_kg for t in aging), 1),
            empty_count=sum(1 for t in tanks if t.status == "empty"),
            in_3m_kg=within(3), in_6m_kg=within(6), in_12m_kg=within(12),
        )
        return TankMapOut(aging_months=self.months, summary=summary, buildings=buildings)

    # ------------------------------------------------------------------ 쓰기
    def add_building(self, body: BuildingIn, actor: str = "관리자") -> TankMapOut:
        name = body.name.strip()
        if any(t.building == name for t in self.tanks(fresh=True)):
            raise ValidationFailed(f"'{name}' 건물이 이미 있어요. 다른 이름을 써 주세요.")
        stamp = now()
        rows = []
        for i in range(body.count):
            rows.append({
                "tank_id": f"{name}-{i + 1:02d}", "building": name, "no": i + 1,
                "row": i // body.per_row + 1, "col": i % body.per_row + 1,
                "capacity_kg": body.capacity_kg or None, "current_kg": 0, "product": body.product,
                "filled_on": "", "memo": "", "updated_at": stamp,
            })
        self.repo.insert_many(rows)
        self.ctx.logs.write("저장소 건물 추가", name, f"저장소 {body.count}개", actor=actor)
        return self.map()

    def update(self, tank_id: str, patch: TankPatch, actor: str = "관리자") -> TankOut:
        cur = self.repo.get(tank_id, fresh=True)
        if cur is None:
            raise NotFoundError("저장소를 찾지 못했어요.")
        changes: dict[str, Any] = {k: v for k, v in patch.model_dump(exclude_unset=True).items()}
        if "filled_on" in changes:
            text = (changes["filled_on"] or "").strip()
            if text and parse_filled(text) is None:
                raise ValidationFailed("담근 날은 2024-06 처럼 적어 주세요.")
            fd = parse_filled(text)
            if fd and fd > today():
                raise ValidationFailed("담근 날이 오늘보다 뒤예요.")
            changes["filled_on"] = text
        if changes.get("current_kg") and changes.get("capacity_kg") is None:
            cap = float(cur.get("capacity_kg") or 0)
            if cap and changes["current_kg"] > cap * 1.2:
                raise ValidationFailed(f"용량({cap:g}kg)보다 너무 많아요. 숫자를 확인해 주세요.")
        if changes.get("current_kg") == 0:
            changes.setdefault("filled_on", "")  # 비우면 담근 날도 지움
        changes["updated_at"] = now()
        self.repo.update((tank_id,), changes)
        before = f"{cur.get('current_kg') or 0:g}kg / {cur.get('filled_on') or '-'}"
        after_d = {**cur, **changes}
        self.ctx.logs.write("저장소 수정", tank_id, f"{before} → {after_d.get('current_kg') or 0:g}kg / {after_d.get('filled_on') or '-'}", actor=actor)
        return self._tank(after_d, today(), self.months)

    def delete_building(self, name: str, actor: str = "관리자") -> TankMapOut:
        ts = [t for t in self.tanks(fresh=True) if t.building == name]
        if not ts:
            raise NotFoundError("건물을 찾지 못했어요.")
        if any(t.current_kg > 0 for t in ts):
            raise ValidationFailed("젓갈이 들어 있는 저장소가 있어서 지울 수 없어요. 먼저 비워 주세요.")
        self.repo.delete_many([(t.tank_id,) for t in ts])
        self.ctx.logs.write("저장소 건물 삭제", name, f"저장소 {len(ts)}개", actor=actor)
        return self.map()

    # ------------------------------------------------------------------ 아침 브리핑
    def briefing_lines(self) -> list[str]:
        ts = self.tanks()
        if not ts:
            return []
        ready = [t for t in ts if t.status == "ready"]
        this_month = [t for t in ts if t.status == "aging" and t.months_left is not None and t.months_left <= 1]
        out = []
        if ready:
            out.append(f"숙성 끝 저장소 {len(ready)}개 · {sum(t.current_kg for t in ready):,.0f}kg 출하 가능")
        if this_month:
            names = ", ".join(f"{t.building} {t.no}번" for t in this_month[:5])
            out.append(f"곧 숙성 끝: {names}")
        return out
