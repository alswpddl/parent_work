"""숙성 저장소 지도: 건물 추가 → 담근 날·양 입력 → 숙성 끝/중/비어 있음 계산"""
from datetime import date

import pytest

from app.core.errors import ValidationFailed
from app.modules.q4_inventory.aging import BuildingIn, TankPatch, add_months, months_between, parse_filled


def test_parse_filled():
    assert parse_filled("2024-06") == date(2024, 6, 15)
    assert parse_filled("24.6") == date(2024, 6, 15)
    assert parse_filled("2024년 6월") == date(2024, 6, 15)
    assert parse_filled("2024-06-03") == date(2024, 6, 3)
    assert parse_filled("") is None and parse_filled("모름") is None
    assert add_months(date(2024, 6, 15), 24) == date(2026, 6, 15)
    assert months_between(date(2026, 1, 10), date(2026, 6, 15)) == 6


def test_tank_map_flow(full_ctx, monkeypatch):
    import app.modules.q4_inventory.aging as aging_mod

    monkeypatch.setattr(aging_mod, "today", lambda: date(2026, 11, 28))
    svc = full_ctx.services["aging"]
    m = svc.add_building(BuildingIn(name="1동", count=10, per_row=5, capacity_kg=1000))
    b = m.buildings[0]
    assert (b.name, b.rows, b.cols, len(b.tanks)) == ("1동", 2, 5, 10)
    assert m.summary.empty_count == 10
    with pytest.raises(ValidationFailed):
        svc.add_building(BuildingIn(name="1동", count=3))

    svc.update("1동-01", TankPatch(current_kg=900, filled_on="2024-06"))  # 2026-06 끝 → 숙성 끝
    t2 = svc.update("1동-02", TankPatch(current_kg=800, filled_on="2025-03"))  # 2027-03 → 4개월 남음
    assert t2.status == "aging" and t2.months_left == 4 and 0 < t2.progress < 100
    svc.update("1동-03", TankPatch(current_kg=500))  # 담근 날 모름 → 숙성 중
    with pytest.raises(ValidationFailed, match="2024-06"):
        svc.update("1동-04", TankPatch(filled_on="언젠가"))
    with pytest.raises(ValidationFailed, match="용량"):
        svc.update("1동-04", TankPatch(current_kg=5000))

    m = svc.map()
    s = m.summary
    assert (s.ready_count, s.aging_count, s.empty_count) == (1, 2, 7)
    assert s.ready_kg == 900 and s.in_6m_kg == 1700 and s.in_3m_kg == 900
    assert any("숙성 끝 저장소 1개" in line for line in svc.briefing_lines())

    # 비우면 담근 날도 지워지고 비어 있음
    t = svc.update("1동-01", TankPatch(current_kg=0))
    assert t.status == "empty" and t.filled_on == ""
    with pytest.raises(ValidationFailed, match="비워"):
        svc.delete_building("1동")
