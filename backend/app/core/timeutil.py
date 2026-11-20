"""한국 시간(KST) 고정 유틸. 한국은 서머타임이 없어 고정 오프셋으로 충분하다."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9), "KST")
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]  # date.weekday() 순서


def now() -> datetime:
    return datetime.now(KST).replace(microsecond=0)


def today() -> date:
    return now().date()


def fmt_date_ko(d: date | None) -> str:
    """2026-11-20 -> '11/20(금)'"""
    if d is None:
        return "날짜 미정"
    return f"{d.month}/{d.day}({WEEKDAYS_KO[d.weekday()]})"
