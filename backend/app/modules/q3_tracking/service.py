"""운송장 역등록.

택배사 프로그램에서 송장 출력 후 받은 엑셀을 올리면
1) 각 줄에서 우리 주문번호(O-YYYYMMDD-NNN)를 찾고 — 업로드 양식에 주문번호 열을 넣어 보냈기 때문에 대부분 그대로 돌아온다
2) 없으면 받는분 이름 + 전화번호 뒷자리로 출고 대기 택배 주문과 맞춘다
3) 미리보기에서 확인 → [등록] 하면 송장번호 기록 + 출고완료 처리 (→ 3분기 알림톡 자동 발송)
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from ...core.errors import ValidationFailed
from ...core.uploads import PreviewStore, cell_text, find_table, pick, read_rows
from ...schemas.order import OrderOut

CARRIERS = ["CJ대한통운", "로젠택배", "한진택배", "롯데택배", "우체국택배", "경동택배", "대신택배", "기타"]

HINTS = {
    "tracking": ["운송장번호", "송장번호", "운송장", "운송장 번호", "송장 번호", "등기번호"],
    "name": ["받는분", "받는분성명", "수하인명", "수하인", "수취인", "수취인명", "수령인", "받는 분"],
    "phone": ["받는분전화번호", "받는분 전화", "수하인전화", "수하인전화번호", "수취인연락처", "수취인전화번호", "전화번호", "휴대폰", "연락처"],
    "order_id": ["주문번호", "고객주문번호", "참조번호", "주문 번호"],
}
ORDER_ID_RE = re.compile(r"O-\d{8}-\d{3}")


class TrackingRow(BaseModel):
    row_no: int
    tracking_no: str
    name: str
    phone: str
    order_id: str | None = None
    customer_name: str = ""
    status: str  # 매칭 / 확인필요 / 못찾음 / 이미등록 / 송장없음
    message: str = ""
    candidates: list[str] = []


class TrackingPreview(BaseModel):
    import_id: str
    carrier: str
    rows: list[TrackingRow]
    matched: int
    total: int


class TrackingConfirmIn(BaseModel):
    carrier: str = Field(min_length=1)
    picks: dict[int, str] = Field(default_factory=dict, description="{row_no: order_id} — 미리보기에서 사람이 고르거나 고친 값")
    skip_rows: list[int] = Field(default_factory=list)


class TrackingResult(BaseModel):
    registered: int
    shipped: int
    skipped: int
    errors: list[str]


class TrackingIn(BaseModel):
    carrier: str = Field(min_length=1)
    tracking_no: str = Field(min_length=4, max_length=40)
    ship: bool = True


class TruckIn(BaseModel):
    truck_no: str = Field(min_length=2, max_length=30)
    driver_phone: str = Field(default="", max_length=20)
    ship: bool = True


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _clean_tracking(v: Any) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", cell_text(v))


class TrackingService:
    def __init__(self, ctx: Any):
        self.ctx = ctx
        self.previews = PreviewStore()

    # ---------------------------------------------------------------- 엑셀
    def preview(self, filename: str, data: bytes, carrier: str) -> TrackingPreview:
        table = find_table(read_rows(filename, data), HINTS)
        orders = self.ctx.orders.query(include_cancelled=True)
        by_id = {o.order_id: o for o in orders}
        pending = [o for o in orders if o.ship_method == "택배" and o.status != "취소" and not o.tracking_no]

        rows: list[TrackingRow] = []
        for i, r in enumerate(table.rows, start=table.header_row + 1):
            tracking = _clean_tracking(pick(r, HINTS["tracking"]))
            name = cell_text(pick(r, HINTS["name"]))
            phone = cell_text(pick(r, HINTS["phone"]))
            row = TrackingRow(row_no=i, tracking_no=tracking, name=name, phone=phone, status="못찾음")
            if not tracking:
                row.status, row.message = "송장없음", "송장번호 칸이 비어 있어요"
                rows.append(row)
                continue

            oid = None
            for v in r.values():
                m = ORDER_ID_RE.search(cell_text(v))
                if m:
                    oid = m.group(0)
                    break
            if oid and oid in by_id:
                self._set_match(row, by_id[oid])
            else:
                cands = self._match_by_person(pending, name, phone)
                if len(cands) == 1:
                    self._set_match(row, cands[0])
                    row.message = "이름·전화번호로 찾았어요"
                elif len(cands) > 1:
                    row.status, row.message = "확인필요", "같은 분 주문이 여러 건이에요"
                    row.candidates = [c.order_id for c in cands]
                else:
                    row.message = "맞는 주문을 찾지 못했어요"
            rows.append(row)

        matched = sum(1 for r in rows if r.status == "매칭")
        preview = TrackingPreview(import_id="", carrier=carrier, rows=rows, matched=matched, total=len(rows))
        preview.import_id = self.previews.put(preview)
        return preview

    @staticmethod
    def _set_match(row: TrackingRow, o: OrderOut) -> None:
        row.order_id = o.order_id
        row.customer_name = o.customer_name
        if o.status == "취소":
            row.status, row.message = "못찾음", "취소된 주문이에요"
        elif o.tracking_no and o.tracking_no != row.tracking_no:
            row.status, row.message = "이미등록", f"이미 송장 {o.tracking_no} 가 있어요"
        elif o.tracking_no == row.tracking_no:
            row.status, row.message = "이미등록", "같은 송장이 이미 등록돼 있어요"
        else:
            row.status = "매칭"

    @staticmethod
    def _match_by_person(orders: list[OrderOut], name: str, phone: str) -> list[OrderOut]:
        if not name and not phone:
            return []
        tail = _digits(phone)[-4:]
        out = []
        for o in orders:
            name_ok = bool(name) and name.replace(" ", "") in {o.recipient.replace(" ", ""), o.customer_name.replace(" ", "")}
            phone_ok = bool(tail) and _digits(o.phone).endswith(tail)
            if (name_ok and phone_ok) or (name_ok and not tail) or (phone_ok and not name):
                out.append(o)
        return out

    def confirm(self, import_id: str, body: TrackingConfirmIn) -> TrackingResult:
        preview: TrackingPreview = self.previews.get(import_id)
        skip = set(body.skip_rows)
        registered = shipped = skipped = 0
        errors: list[str] = []
        seen: set[str] = set()
        for row in preview.rows:
            oid = body.picks.get(row.row_no) or (row.order_id if row.status == "매칭" else None)
            if row.row_no in skip or not oid or not row.tracking_no:
                skipped += 1
                continue
            if oid in seen:  # 한 주문에 송장 여러 장이면 첫 장만 (나머지는 메모로 남김)
                errors.append(f"{row.row_no}행: {oid} 는 이미 앞 줄에서 등록했어요 (송장 {row.tracking_no})")
                continue
            seen.add(oid)
            try:
                r = self.set_tracking(oid, TrackingIn(carrier=body.carrier, tracking_no=row.tracking_no, ship=True))
                registered += 1
                shipped += 1 if r.status == "출고완료" else 0
            except Exception as e:  # noqa: BLE001 — 한 줄 실패가 전체를 막지 않게
                errors.append(f"{row.row_no}행 {oid}: {getattr(e, 'message', str(e))}")
        self.previews.pop(import_id)
        self.ctx.logs.write("송장 일괄등록", body.carrier, f"{registered}건 등록, {skipped}건 건너뜀")
        return TrackingResult(registered=registered, shipped=shipped, skipped=skipped, errors=errors)

    # ---------------------------------------------------------------- 직접 입력
    def set_tracking(self, order_id: str, body: TrackingIn) -> OrderOut:
        o = self.ctx.orders.get(order_id, fresh=True)
        if o.status == "취소":
            raise ValidationFailed("취소된 주문이에요.")
        out = self.ctx.orders.set_fields(
            order_id, {"carrier": body.carrier, "tracking_no": _clean_tracking(body.tracking_no)},
            publish=None, log_action="송장 등록",
        )
        if body.ship and out.status != "출고완료":
            return self.ctx.orders.ship(order_id)  # order.shipped → 알림톡
        self.ctx.bus.publish("order.shipping_info", {"order": out})  # 이미 출고된 주문에 송장만 추가
        return out

    def set_truck(self, order_id: str, body: TruckIn) -> OrderOut:
        o = self.ctx.orders.get(order_id, fresh=True)
        if o.status == "취소":
            raise ValidationFailed("취소된 주문이에요.")
        out = self.ctx.orders.set_fields(
            order_id, {"truck_no": body.truck_no.strip(), "driver_phone": body.driver_phone.strip()},
            publish=None, log_action="차량 정보",
        )
        if body.ship and out.status != "출고완료":
            return self.ctx.orders.ship(order_id)
        self.ctx.bus.publish("order.shipping_info", {"order": out})
        return out
