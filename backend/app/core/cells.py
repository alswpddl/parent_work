"""시트 셀 값 <-> 파이썬 값 변환.

시트에는 RAW 모드로 쓴다. RAW 는 문자열을 그대로 문자열로 저장하므로
'010-1234-5678' 이나 '012345' 의 앞자리 0 이 사라지지 않는다.
숫자는 JSON 숫자로 보내므로 시트에서도 숫자로 저장돼 SUMIF 등이 그대로 동작한다.
날짜는 'YYYY-MM-DD' 문자열로 저장해 정렬이 자연스럽다.

읽을 때는 UNFORMATTED_VALUE + 날짜 FORMATTED_STRING 으로 읽으므로
부모님이 손으로 친 날짜(시트가 날짜로 인식한 값)도 문자열로 들어온다.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from .sheet_schema import ColType
from .timeutil import KST

_TRUE = {"true", "1", "y", "yes", "o", "예", "네", "사용", "✓", "v"}
_FALSE = {"false", "0", "n", "no", "x", "아니오", "미사용", ""}
_SHEETS_EPOCH = date(1899, 12, 30)

_DATE_PATTERNS = [
    re.compile(r"^\s*(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})\s*일?\s*"),
]


def _parse_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):  # 시트 날짜 일련번호
        return _SHEETS_EPOCH + timedelta(days=int(v))
    s = str(v).strip()
    for pat in _DATE_PATTERNS:
        m = pat.match(s)
        if m:
            y, mo, d = (int(x) for x in m.groups())
            try:
                return date(y, mo, d)
            except ValueError:
                return None
    return None


def _parse_datetime(v: Any) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=KST)
    if isinstance(v, (int, float)):
        base = datetime(1899, 12, 30, tzinfo=KST)
        return base + timedelta(days=float(v))
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y. %m. %d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=KST)
    except ValueError:
        pass
    d = _parse_date(s)
    return datetime(d.year, d.month, d.day, tzinfo=KST) if d else None


def from_cell(t: ColType, v: Any) -> Any:
    """시트 값 -> 파이썬 값. 빈칸은 str 이면 '', 나머지는 None."""
    if t == "str":
        if v is None:
            return ""
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).strip()
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if t == "int":
        try:
            return int(round(float(str(v).replace(",", ""))))
        except ValueError:
            return None
    if t == "float":
        try:
            return float(str(v).replace(",", ""))
        except ValueError:
            return None
    if t == "bool":
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in _TRUE:
            return True
        if s in _FALSE:
            return False
        return None
    if t == "date":
        return _parse_date(v)
    if t == "datetime":
        return _parse_datetime(v)
    return v


def to_cell(t: ColType, v: Any) -> Any:
    """파이썬 값 -> 시트에 RAW 로 쓸 값."""
    if v is None:
        return ""
    if t == "str":
        return str(v)
    if t == "int":
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return ""
    if t == "float":
        try:
            f = float(v)
        except (TypeError, ValueError):
            return ""
        return round(f, 3)
    if t == "bool":
        return bool(v)
    if t == "date":
        d = _parse_date(v)
        return d.isoformat() if d else ""
    if t == "datetime":
        dt = _parse_datetime(v)
        return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S") if dt else ""
    return v
