"""거래처·품목 이름 매칭.

카톡 주문은 '한솥', '한솥 사장님', '참기름 큰거', '1.8리터' 처럼 제각각이라
1) 정규화(공백 제거, 리터→l, 키로→kg 등) 후
2) 정확 일치 / 별칭 일치 / 포함 관계 / 유사도(difflib) 순으로 점수를 매긴다.
점수 0.8 이상이면 자동 매칭, 그보다 낮으면 후보만 보여주고 사람이 고르게 한다.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..schemas.customer import CustomerOut
from ..schemas.order import Candidate
from ..schemas.product import ProductOut

AUTO_MATCH = 0.8

_SUBS = [
    (re.compile(r"리터|ℓ|liter|litre"), "l"),
    (re.compile(r"킬로그램|킬로|키로|㎏"), "kg"),
    (re.compile(r"그램|ｇ"), "g"),
    (re.compile(r"(사장님|사모님|대표님|실장님|님)$"), ""),
    (re.compile(r"\(주\)|㈜|주식회사"), ""),
]


def normalize(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\s+", "", s)
    for pat, rep in _SUBS:
        s = pat.sub(rep, s)
    return re.sub(r"[~!.,·\-_/()\[\]'\"]+$", "", s)


def norm_spec(s: str) -> str:
    """규격 비교용: '1.8 L' '1.8리터' -> '1.8l'"""
    return normalize(s).rstrip(".")


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _score_names(query: str, names: list[str]) -> float:
    q = normalize(query)
    if not q:
        return 0.0
    best = 0.0
    for n in names:
        nn = normalize(n)
        if not nn:
            continue
        if q == nn:
            return 1.0
        if len(nn) >= 2 and (nn in q or q in nn):
            # 짧은 이름이 긴 문장에 포함된 경우: 길이 비율로 감점
            best = max(best, 0.85 + 0.1 * min(len(nn), len(q)) / max(len(nn), len(q)))
        else:
            best = max(best, _ratio(q, nn) * 0.9)
    return min(best, 1.0)


# ---------------------------------------------------------------------------
# 거래처
# ---------------------------------------------------------------------------
def match_customer(query: str, customers: list[CustomerOut], limit: int = 3) -> tuple[CustomerOut | None, list[Candidate]]:
    scored = []
    for c in customers:
        s = _score_names(query, [c.name, *c.alias_list()])
        if s > 0.35:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    cands = [Candidate(id=c.customer_id, label=c.name, score=round(s, 2)) for s, c in scored[:limit]]
    best = scored[0][1] if scored and scored[0][0] >= AUTO_MATCH else None
    # 1·2등 점수가 거의 같으면 자동 매칭하지 않는다
    if best and len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
        best = None
    return best, cands


def find_customer_in_text(text: str, customers: list[CustomerOut]) -> CustomerOut | None:
    """메시지 본문에 거래처명/별칭이 그대로 들어있는지 (규칙 파서용). 긴 이름 우선."""
    t = normalize(text)
    pairs = []
    for c in customers:
        for n in [c.name, *c.alias_list()]:
            nn = normalize(n)
            if len(nn) >= 2 and nn in t:
                pairs.append((len(nn), c))
    if not pairs:
        return None
    pairs.sort(key=lambda x: -x[0])
    return pairs[0][1]


# ---------------------------------------------------------------------------
# 품목
# ---------------------------------------------------------------------------
def match_product(
    raw_name: str, products: list[ProductOut], spec: str = "", limit: int = 3
) -> tuple[ProductOut | None, list[Candidate]]:
    q_full = normalize(f"{raw_name}{spec}")
    q_spec = norm_spec(spec) if spec else ""
    scored = []
    for p in products:
        ps = norm_spec(p.spec)
        # 규격이 메시지에 있으면 반드시 맞아야 한다 (1.8L 을 5kg 로 잘못 붙이지 않게)
        spec_in_query = bool(ps) and (ps == q_spec or ps in q_full)
        if q_spec and ps and not spec_in_query:
            continue
        name_score = _score_names(raw_name, [p.name, p.display_name, *p.alias_list()])
        full_score = _score_names(q_full, [p.display_name, *p.alias_list()])
        s = max(name_score, full_score)
        if spec_in_query:
            s = min(1.0, s + 0.1)
        if s > 0.35:
            scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    cands = [Candidate(id=p.sku, label=p.display_name, score=round(s, 2)) for s, p in scored[:limit]]
    best = scored[0][1] if scored and scored[0][0] >= AUTO_MATCH else None
    if best and len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
        best = None  # 참기름 1.8L / 들기름 1.8L 처럼 헷갈리면 사람에게 묻는다
    return best, cands
