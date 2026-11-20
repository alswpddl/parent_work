"""카톡 비정형 주문 파서.

1) AI 파서: Claude 가 거래처/품목 목록을 보고 구조화 (record_order 도구)
2) 규칙 파서: API 키가 없거나 AI 호출이 실패하면 자동으로 대신 사용
결과는 ParsedOrder 로 통일하고, 실제 거래처·품목 매칭과 무게 계산은 OrderService 가 한다.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

from ...core.timeutil import WEEKDAYS_KO, today as kst_today
from ...integrations.claude_client import ClaudeClient, ClaudeUnavailable
from ...schemas.customer import CustomerOut
from ...schemas.product import ProductOut
from ...services.matching import find_customer_in_text, norm_spec, normalize
from ...services.order_service import ParsedItem, ParsedOrder

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "order_parse.md"


# ---------------------------------------------------------------------------
# AI 파서
# ---------------------------------------------------------------------------
ORDER_TOOL = {
    "name": "record_order",
    "description": (
        "카카오톡 주문 메시지에서 뽑은 주문 1건을 기록한다. 거래처와 품목은 제공된 목록의 id/sku 로 연결하고, "
        "확실하지 않으면 null 로 두어 사람이 고르게 한다. 메시지에 없는 정보는 빈 문자열로 둔다."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "customer_id": {"type": ["string", "null"], "description": "customers 목록의 id. 애매하면 null"},
            "customer_name": {"type": "string", "description": "메시지에서 읽은 거래처 이름"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": ["string", "null"], "description": "products 목록의 sku. 애매하면 null"},
                        "raw_name": {"type": "string", "description": "메시지에 적힌 품목 표현 그대로"},
                        "spec": {"type": "string", "description": "규격 (예: 1.8L, 5kg). 없으면 빈 문자열"},
                        "qty": {"type": "integer", "minimum": 0, "description": "개수"},
                    },
                    "required": ["raw_name", "qty"],
                },
            },
            "address": {"type": "string"},
            "phone": {"type": "string"},
            "due_date": {"type": "string", "description": "YYYY-MM-DD 또는 빈 문자열"},
            "note": {"type": "string"},
        },
        "required": ["customer_name", "items", "address", "due_date", "note"],
    },
}


def build_ai_user_message(text: str, customers: list[CustomerOut], products: list[ProductOut], day: date) -> str:
    cust = [{"id": c.customer_id, "name": c.name, "aliases": c.alias_list()} for c in customers]
    prod = [
        {"sku": p.sku, "name": p.name, "spec": p.spec, "aliases": p.alias_list(), "units_per_box": p.units_per_box}
        for p in products
    ]
    return (
        f"<today>{day.isoformat()} ({WEEKDAYS_KO[day.weekday()]}요일)</today>\n"
        f"<customers>{json.dumps(cust, ensure_ascii=False)}</customers>\n"
        f"<products>{json.dumps(prod, ensure_ascii=False)}</products>\n"
        f"<message>\n{text}\n</message>"
    )


def parse_with_ai(
    client: ClaudeClient, text: str, customers: list[CustomerOut], products: list[ProductOut], day: date | None = None
) -> ParsedOrder:
    day = day or kst_today()
    system = PROMPT_PATH.read_text(encoding="utf-8")
    data = client.call_tool(system=system, user=build_ai_user_message(text, customers, products, day), tool=ORDER_TOOL)
    return _from_ai_dict(data)


def _from_ai_dict(data: dict) -> ParsedOrder:
    items: list[ParsedItem] = []
    for it in data.get("items") or []:
        if not isinstance(it, dict):
            continue
        try:
            qty = int(it.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0
        items.append(
            ParsedItem(
                raw_name=str(it.get("raw_name") or "").strip(),
                qty=max(0, qty),
                spec=str(it.get("spec") or "").strip(),
                sku=(str(it["sku"]).strip() or None) if it.get("sku") else None,
            )
        )
    due = None
    raw_due = str(data.get("due_date") or "").strip()
    if raw_due:
        try:
            due = date.fromisoformat(raw_due[:10])
        except ValueError:
            due = None
    cid = data.get("customer_id")
    return ParsedOrder(
        customer_id=str(cid).strip() if cid else None,
        customer_name=str(data.get("customer_name") or "").strip(),
        items=items,
        address=str(data.get("address") or "").strip(),
        phone=str(data.get("phone") or "").strip(),
        due_date=due,
        note=str(data.get("note") or "").strip(),
    )


# ---------------------------------------------------------------------------
# 규칙 파서 (AI 대체용)
# ---------------------------------------------------------------------------
_QTY = re.compile(r"(\d+)\s*(개|통|병|박스|box|ea|봉|포|말)?", re.IGNORECASE)
_PHONE = re.compile(r"(01[016789])[-.\s]?(\d{3,4})[-.\s]?(\d{4})")
_NOTE_HINT = re.compile(r"(부탁|주의|문\s*앞|오전|오후|시\s*까지|시\s*전|전화|연락|경비실|포장)")
_ADDR_HINT = re.compile(
    r"(\S+(특별시|광역시|시|군|구)\s*\S*(구|동|읍|면|리|로|길))"
    r"|(\S+(로|길)\s*\d+(-\d+)?(?![\d\-])(?!\s*(개|통|병|박스|봉|포)))"
    r"|^\s*(주소|배송지)\s*[:：]"
)
_DATE_MD = re.compile(r"(?<![\d.])(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_DATE_SLASH = re.compile(r"(?<![\d.])(\d{1,2})\s*/\s*(\d{1,2})(?![\d.]*\s*(?:l|L|kg|KG|리터|키로|g))")
_DOW = re.compile(r"(다음\s*주\s*|담주\s*)?([월화수목금토일])\s*요일")


def resolve_due_date(text: str, day: date | None = None) -> date | None:
    base = day or kst_today()
    if "글피" in text:
        return base + timedelta(days=3)
    if "모레" in text:
        return base + timedelta(days=2)
    if "내일" in text:
        return base + timedelta(days=1)
    if "오늘" in text:
        return base
    m = _DATE_MD.search(text) or _DATE_SLASH.search(text)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        try:
            cand = date(base.year, mo, d)
        except ValueError:
            cand = None
        if cand:
            if (base - cand).days > 60:  # 12월에 '1/5' 라고 하면 내년
                cand = date(base.year + 1, mo, d)
            return cand
    m = _DOW.search(text)
    if m:
        target = WEEKDAYS_KO.index(m.group(2))
        diff = (target - base.weekday()) % 7 or 7
        if m.group(1):
            diff += 7
        return base + timedelta(days=diff)
    return None


def _segments(text: str) -> list[str]:
    parts = re.split(r"[\n,，、;/]+", text)
    out: list[str] = []
    for p in parts:
        # "참기름1.8L 10개 들기름1.8L 5개" 처럼 한 줄에 여러 개면 수량 단위 뒤에서 자른다
        out.extend(s for s in re.split(r"(?<=[개통병봉포])\s+", p) if s.strip())
    return [s.strip() for s in out if s.strip()]


def parse_with_rules(
    text: str, customers: list[CustomerOut], products: list[ProductOut], day: date | None = None
) -> ParsedOrder:
    cust = find_customer_in_text(text, customers)
    items: dict[str, ParsedItem] = {}
    unknown: list[ParsedItem] = []

    for seg in _segments(text):
        nseg = normalize(seg)
        # 규격이 들어 있는 품목 후보
        cands = [p for p in products if p.spec and norm_spec(p.spec) in nseg]
        named = [p for p in cands if normalize(p.name) in nseg or any(normalize(a) in nseg for a in p.alias_list())]
        pool = named or cands
        if not pool:
            # 규격 없이 이름만 있는 경우 (그 이름의 품목이 하나뿐일 때만 확정)
            by_name = [p for p in products if len(normalize(p.name)) >= 2 and normalize(p.name) in nseg]
            if not by_name:
                continue
            qty = _qty_after_removing(nseg, [normalize(p.name) for p in by_name])
            if qty is None:
                continue
            if len(by_name) == 1:
                _add(items, by_name[0], qty, seg)
            else:
                unknown.append(ParsedItem(raw_name=seg, qty=qty))
            continue

        pool.sort(key=lambda p: -len(norm_spec(p.spec)))
        p = pool[0]
        qty = _qty_after_removing(nseg, [norm_spec(p.spec), normalize(p.name)])
        if qty is None:
            continue
        if len(named) > 1 and len({x.sku for x in named}) > 1 and named[0].spec == named[1].spec:
            unknown.append(ParsedItem(raw_name=seg, qty=qty, spec=p.spec))
        elif not named and len({x.name for x in cands}) > 1:
            unknown.append(ParsedItem(raw_name=seg, qty=qty, spec=p.spec))  # 규격만 있고 품목명이 없음
        else:
            _add(items, p, qty, seg)

    lines = text.splitlines()
    spec_words = [norm_spec(p.spec) for p in products if p.spec]
    addr = next(
        (l.strip() for l in lines if _ADDR_HINT.search(l) and not any(s and s in normalize(l) for s in spec_words)),
        "",
    )
    addr = re.sub(r"^(주소|배송지|받는\s*곳)\s*[:：]?\s*", "", addr)
    phone_m = _PHONE.search(text)
    notes = [
        l.strip()
        for l in lines
        if _NOTE_HINT.search(l) and not any(s and s in normalize(l) for s in spec_words) and l.strip() != addr
    ]
    return ParsedOrder(
        customer_id=cust.customer_id if cust else None,
        customer_name=cust.name if cust else "",
        items=list(items.values()) + unknown,
        address=addr,
        phone="-".join(phone_m.groups()) if phone_m else "",
        due_date=resolve_due_date(text, day),
        note=" / ".join(notes)[:200],
    )


def _qty_after_removing(nseg: str, words: list[str]) -> int | None:
    rest = nseg
    for w in sorted((w for w in words if w), key=len, reverse=True):
        rest = rest.replace(w, " ")
    m = _QTY.search(rest)
    if not m:
        return None
    q = int(m.group(1))
    return q if 0 < q <= 100000 else None


def _add(items: dict[str, ParsedItem], p: ProductOut, qty: int, raw: str) -> None:
    if p.sku in items:
        items[p.sku].qty += qty
    else:
        items[p.sku] = ParsedItem(raw_name=raw, qty=qty, spec=p.spec, sku=p.sku)


# ---------------------------------------------------------------------------
# 통합 진입점
# ---------------------------------------------------------------------------
def parse_order_text(
    text: str,
    customers: list[CustomerOut],
    products: list[ProductOut],
    client: ClaudeClient | None,
    *,
    use_ai: bool = True,
    day: date | None = None,
) -> tuple[ParsedOrder, str, list[str]]:
    """(결과, 'ai'|'rule', 경고 목록)"""
    warnings: list[str] = []
    if use_ai and client is not None and client.enabled:
        try:
            return parse_with_ai(client, text, customers, products, day), "ai", warnings
        except ClaudeUnavailable as e:
            log.warning("AI 파싱 실패 → 규칙 파서 사용: %s", e)
            warnings.append("AI 정리가 안 돼서 간단 규칙으로 정리했어요. 품목과 수량을 꼭 확인해 주세요.")
    elif use_ai:
        warnings.append("AI 키가 설정되지 않아 간단 규칙으로 정리했어요.")
    return parse_with_rules(text, customers, products, day), "rule", warnings
