"""월말 정산 · 거래명세표.

- 대상: 그 달에 '출고완료'된 B2B 주문 (출고일시 기준, 비어 있으면 납기일 → 접수일)
  개인(B2C) 고객 주문과 '입금확인'된 주문(선입금)은 빠진다
- 세액: 품목 '과세구분'이 면세가 아니면 공급가액의 10% (원 단위 반올림)
- 정산ID: S-202611-C0001. 다시 만들면 같은 ID 를 덮어쓴다. 단, 이미 발송·수금된 건은 force 없이는 건드리지 않음
- 주문장 '정산ID' 칸에 연결해 두므로, 시트에서도 어느 주문이 어느 명세서에 들어갔는지 볼 수 있다
- 발송: 이메일(PDF 첨부) / 알림톡(서명된 PDF 링크, 30일 유효)
"""

from __future__ import annotations

import calendar
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from ...core.briefing import BriefingSection
from ...core.errors import NotFoundError, ValidationFailed
from ...core.repository import Repository
from ...core.sheet_schema import SETTLEMENTS
from ...core.signing import sign
from ...core.timeutil import now, today
from ...integrations.mailer import MailError
from ...schemas.order import OrderOut
from .statement_pdf import Party, StatementData, StatementLine, build_statement_pdf

log = logging.getLogger(__name__)
LINK_TTL = 30 * 24 * 3600
STATUSES = ("생성", "발송완료", "수금완료")


class SettlementOut(BaseModel):
    settlement_id: str
    period: str
    customer_id: str
    customer_name: str
    order_count: int
    supply_amount: int
    vat: int
    total: int
    status: str
    sent_at: datetime | None = None
    paid_at: date | None = None
    memo: str = ""
    has_email: bool = False
    has_phone: bool = False


class GenerateIn(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    force: bool = False


class GenerateOut(BaseModel):
    period: str
    created: int
    updated: int
    kept: list[str]  # 이미 발송·수금돼서 건드리지 않은 정산ID
    warnings: list[str]
    settlements: list[SettlementOut]


class SendIn(BaseModel):
    via: list[str] = Field(default_factory=lambda: ["kakao", "email"], description="kakao / email")


class SendOut(BaseModel):
    settlement_id: str
    results: dict[str, str]  # {"email": "성공" | 이유, "kakao": ...}
    status: str


class SettlementPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(생성|발송완료|수금완료)$")
    paid_at: date | None = None
    memo: str | None = None


def month_range(period: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period or ""):
        raise ValidationFailed("정산월은 2026-11 형식으로 넣어 주세요.")
    y, m = int(period[:4]), int(period[5:])
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def prev_period(day: date) -> str:
    first = day.replace(day=1)
    last_month = first - timedelta(days=1)
    return f"{last_month:%Y-%m}"


def _order_day(o: OrderOut) -> date | None:
    if o.shipped_at:
        return o.shipped_at.date()
    return o.due_date or (o.created_at.date() if o.created_at else None)


class SettlementService:
    def __init__(self, ctx: Any):
        self.ctx = ctx
        self.repo: Repository[dict] = Repository(ctx.sheets, SETTLEMENTS)

    # ---------------------------------------------------------------- 조회
    def _out(self, d: dict) -> SettlementOut:
        c = self.ctx.customers.by_id(d.get("customer_id", "")) if d.get("customer_id") else None
        return SettlementOut(
            settlement_id=d["settlement_id"], period=d.get("period", ""), customer_id=d.get("customer_id", ""),
            customer_name=d.get("customer_name", ""), order_count=d.get("order_count") or 0,
            supply_amount=d.get("supply_amount") or 0, vat=d.get("vat") or 0, total=d.get("total") or 0,
            status=d.get("status") or "생성", sent_at=d.get("sent_at"), paid_at=d.get("paid_at"), memo=d.get("memo", ""),
            has_email=bool(c and "@" in c.email), has_phone=bool(c and c.phone),
        )

    def list_settlements(self, period: str | None = None) -> list[SettlementOut]:
        rows = [d for d in self.repo.rows() if d.get("settlement_id") and (not period or d.get("period") == period)]
        rows.sort(key=lambda d: (d.get("period", ""), d.get("customer_name", "")), reverse=False)
        return [self._out(d) for d in rows]

    def get(self, settlement_id: str) -> SettlementOut:
        d = self.repo.get(settlement_id, fresh=True)
        if not d:
            raise NotFoundError("정산서를 찾을 수 없어요.")
        return self._out(d)

    # ---------------------------------------------------------------- 생성
    def _collect(self, period: str) -> dict[str, list[OrderOut]]:
        start, end = month_range(period)
        by_cust: dict[str, list[OrderOut]] = {}
        # 개인 고객(B2C)은 주문할 때 바로 입금하므로 월말 정산에서 뺀다. 이미 입금 확인한 주문도 뺀다.
        b2c = {c.customer_id for c in self.ctx.customers.list(include_inactive=True) if c.type == "B2C"}
        for o in self.ctx.orders.query(statuses=["출고완료"]):
            d = _order_day(o)
            if not o.customer_id or not d or not (start <= d <= end):
                continue
            if o.customer_id in b2c or o.paid_at:
                continue
            by_cust.setdefault(o.customer_id, []).append(o)
        return by_cust

    def _amounts(self, orders: list[OrderOut]) -> tuple[int, int, list[str]]:
        pmap = self.ctx.products.map()
        supply = vat = 0
        missing: set[str] = set()
        for o in orders:
            for l in o.lines:
                amt = l.amount
                if amt is None:
                    missing.add(l.product_name)
                    continue
                supply += amt
                p = pmap.get(l.sku)
                if p is None or p.is_taxable:
                    vat += round(amt * 0.1)
        return supply, vat, sorted(missing)

    def generate(self, body: GenerateIn) -> GenerateOut:
        period = body.period
        groups = self._collect(period)
        existing = {d["settlement_id"]: d for d in self.repo.rows(fresh=True) if d.get("settlement_id")}
        created = updated = 0
        kept: list[str] = []
        warnings: list[str] = []
        order_links: list[tuple[tuple, dict]] = []
        inserts, updates = [], []

        for cid, orders in sorted(groups.items()):
            sid = f"S-{period.replace('-', '')}-{cid}"
            old = existing.get(sid)
            if old and old.get("status") in ("발송완료", "수금완료") and not body.force:
                kept.append(sid)
                continue
            supply, vat, missing = self._amounts(orders)
            name = orders[0].customer_name
            if missing:
                warnings.append(f"{name}: 단가가 없는 품목 → {', '.join(missing)} (품목 탭에 공급단가를 넣고 다시 만들어 주세요)")
            row = {
                "period": period, "customer_id": cid, "customer_name": name, "order_count": len(orders),
                "supply_amount": supply, "vat": vat, "total": supply + vat, "status": "생성", "sent_at": None,
            }
            if old:
                updates.append(((sid,), row))
                updated += 1
            else:
                inserts.append({"settlement_id": sid, **row, "memo": ""})
                created += 1
            for o in orders:
                for l in o.lines:
                    order_links.append(((o.order_id, l.line_no), {"settlement_id": sid}))

        self.repo.update_many(updates)
        self.repo.insert_many(inserts)
        self.ctx.orders_repo.update_many(order_links)  # 주문장 '정산ID' 연결 (한 번에)
        self.ctx.logs.write("정산 생성", period, f"새로 {created} · 갱신 {updated} · 유지 {len(kept)}")
        return GenerateOut(period=period, created=created, updated=updated, kept=kept, warnings=warnings,
                           settlements=self.list_settlements(period))

    def update(self, settlement_id: str, body: SettlementPatch) -> SettlementOut:
        self.get(settlement_id)
        changes = body.model_dump(exclude_unset=True)
        if changes.get("status") == "수금완료" and "paid_at" not in changes:
            changes["paid_at"] = today()
        if changes.get("status") in ("생성", "발송완료"):
            changes.setdefault("paid_at", None)
        self.repo.update((settlement_id,), changes)
        self.ctx.logs.write("정산 수정", settlement_id, ", ".join(f"{k}={v}" for k, v in changes.items()))
        return self.get(settlement_id)

    # ---------------------------------------------------------------- PDF
    def statement_data(self, settlement_id: str) -> StatementData:
        s = self.get(settlement_id)
        st = self.ctx.settings.load()
        c = self.ctx.customers.by_id(s.customer_id)
        pmap = self.ctx.products.map()
        orders = [o for o in self.ctx.orders.query(statuses=["출고완료"]) if o.settlement_id == settlement_id]
        if not orders:  # 주문장 연결이 없으면 기간·거래처로 다시 모음
            orders = self._collect(s.period).get(s.customer_id, [])
        lines: list[StatementLine] = []
        for o in sorted(orders, key=lambda x: (_order_day(x) or date.min, x.order_id)):
            for l in o.lines:
                amt = l.amount or 0
                p = pmap.get(l.sku)
                vat = round(amt * 0.1) if (p is None or p.is_taxable) else 0
                lines.append(StatementLine(day=_order_day(o), product=l.product_name, qty=l.qty, unit_price=l.unit_price,
                                           amount=amt, vat=vat, order_id=o.order_id))
        return StatementData(
            settlement_id=s.settlement_id, period=s.period, issued=today(),
            supplier=Party(name=st.factory_name or "공장", biz_no=st.company_biz_no, owner=st.company_owner,
                           address=st.factory_address, phone=st.factory_phone, biz_type=st.company_biz_type,
                           biz_item=st.company_biz_item),
            buyer=Party(name=s.customer_name, biz_no=c.biz_no if c else "", owner=c.owner_name if c else "",
                        address=c.address if c else "", phone=c.phone if c else ""),
            lines=lines, supply_total=sum(l.amount for l in lines), vat_total=sum(l.vat for l in lines),
            bank_account=st.bank_account, note=st.statement_note,
        )

    def pdf(self, settlement_id: str) -> tuple[str, bytes]:
        data = self.statement_data(settlement_id)
        filename = f"거래명세표_{data.period}_{data.buyer.name}.pdf"
        return filename, build_statement_pdf(data, self.ctx.config.pdf_font_path)

    def public_link(self, settlement_id: str) -> str:
        token = sign(self.ctx.config.auth_secret, f"stmt:{settlement_id}", LINK_TTL)
        return f"{self.ctx.config.public_api_url}/api/public/statements/{token}"

    # ---------------------------------------------------------------- 발송
    def send(self, settlement_id: str, body: SendIn) -> SendOut:
        s = self.get(settlement_id)
        c = self.ctx.customers.by_id(s.customer_id)
        st = self.ctx.settings.load()
        results: dict[str, str] = {}
        month_label = f"{int(s.period[5:])}월"

        if "email" in body.via:
            if not c or "@" not in c.email:
                results["email"] = "거래처 이메일이 없어요"
            elif not self.ctx.mailer.configured:
                results["email"] = "메일 설정이 없어요"
            else:
                filename, pdf = self.pdf(settlement_id)
                try:
                    self.ctx.mailer.send(
                        to=c.email,
                        subject=f"[{st.factory_name or '공장'}] {s.period} 거래명세표",
                        body=(f"{s.customer_name} 담당자님께,\n\n{month_label} 거래명세표를 첨부해 드립니다.\n"
                              f"합계 금액: {s.total:,}원\n" + (f"입금 계좌: {st.bank_account}\n" if st.bank_account else "")
                              + f"\n감사합니다.\n{st.factory_name} {st.factory_phone}"),
                        attachments=[(filename, pdf, "application/pdf")],
                    )
                    results["email"] = "성공"
                    self.ctx.messages.write(channel="이메일", kind="명세서", to=c.email, order_id=settlement_id, result="성공")
                except MailError as e:
                    results["email"] = str(e)
                    self.ctx.messages.write(channel="이메일", kind="명세서", to=c.email, order_id=settlement_id, result="실패", error=str(e))

        if "kakao" in body.via:
            notify = self.ctx.services.get("notify")
            if notify is None:
                results["kakao"] = "알림톡 모듈(q3_notify)이 꺼져 있어요"
            elif not c or not c.phone:
                results["kakao"] = "거래처 전화번호가 없어요"
            else:
                r = notify.send_template(
                    kind="statement", to=c.phone, label="명세서", ref=settlement_id,
                    variables={
                        "공장명": st.factory_name or "공장", "거래처명": s.customer_name, "정산월": month_label,
                        "건수": str(s.order_count), "합계": f"{s.total:,}", "링크": self.public_link(settlement_id),
                        "입금안내": f"입금 계좌: {st.bank_account}" if st.bank_account else "",
                    },
                )
                results["kakao"] = "성공" if r.sent else r.reason

        if any(v == "성공" for v in results.values()) and s.status == "생성":
            self.repo.update((settlement_id,), {"status": "발송완료", "sent_at": now()})
        return SendOut(settlement_id=settlement_id, results=results, status=self.get(settlement_id).status)

    def send_all(self, period: str, body: SendIn) -> list[SendOut]:
        return [self.send(s.settlement_id, body) for s in self.list_settlements(period) if s.status == "생성"]

    # ---------------------------------------------------------------- 정기작업·브리핑
    def monthly_job(self) -> dict:
        period = prev_period(today())
        r = self.generate(GenerateIn(period=period))
        total = sum(s.total for s in r.settlements)
        text = (f"📑 {int(period[5:])}월 거래명세표 {len(r.settlements)}건을 만들었어요.\n합계 {total:,}원\n"
                "앱 [정산] 화면에서 확인 후 [모두 보내기]를 눌러 주세요.")
        if r.warnings:
            text += f"\n⚠️ 확인 필요 {len(r.warnings)}건 (단가 없는 품목)"
        self.ctx.notifier.send("월말정산", text, path="/settlements", button="정산 보기")
        return {"period": period, "count": len(r.settlements), "total": total}

    def briefing_section(self, ctx: Any, day: date) -> BriefingSection | None:
        this_month = f"{day:%Y-%m}"
        unpaid = [s for s in self.list_settlements() if s.status != "수금완료" and s.period < this_month]
        if not unpaid:
            return None
        total = sum(s.total for s in unpaid)
        names = ", ".join(sorted({s.customer_name for s in unpaid})[:4])
        return BriefingSection(title="미수금", lines=[f"💰 {len(unpaid)}건 {total:,}원 ({names})"], priority=40)
