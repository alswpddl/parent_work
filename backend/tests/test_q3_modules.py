from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook

from app.core.errors import ValidationFailed
from app.modules.q3_marketplace.service import MappingIn, MarketConfirmIn
from app.modules.q3_tracking.service import TrackingConfirmIn, TrackingIn, TruckIn
from app.schemas.order import OrderCreate, OrderItemIn


def _xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _order(ctx, cid="C0001", items=(("SES-18L", 2),), **kw):
    return ctx.orders.create(OrderCreate(customer_id=cid, items=[OrderItemIn(sku=s, qty=q) for s, q in items], **kw))


# ---------------------------------------------------------------- 송장 역등록
def test_tracking_import_by_order_id_ships_and_notifies(full_ctx, http):
    a = _order(full_ctx)
    b = _order(full_ctx, items=(("PER-18L", 1),))
    data = _xlsx([
        ["CJ대한통운 운송장 출력 내역"],  # 제목 줄 (헤더 아님)
        ["받는분", "받는분 전화", "운송장번호", "고객주문번호"],
        ["김사장", "010-1234-5678", 512345678901, a.order_id],
        ["김사장", "010-1234-5678", "5123-4567-8902", b.order_id],
        ["모르는분", "010-0000-0000", "", ""],
    ])
    p = full_ctx.services["tracking"].preview("송장.xlsx", data, "CJ대한통운")
    assert [r.status for r in p.rows] == ["매칭", "매칭", "송장없음"] and p.matched == 2
    assert p.rows[1].tracking_no == "512345678902"

    r = full_ctx.services["tracking"].confirm(p.import_id, TrackingConfirmIn(carrier="CJ대한통운"))
    assert (r.registered, r.shipped, r.skipped) == (2, 2, 1)
    o = full_ctx.orders.get(a.order_id, fresh=True)
    assert o.status == "출고완료" and o.tracking_no == "512345678901" and o.carrier == "CJ대한통운"
    assert o.notified_at is not None  # 알림톡 발송 기록
    sent = http.by("api.solapi.com")
    assert len(sent) == 2
    msg = sent[0]["json"]["messages"][0]
    assert msg["kakaoOptions"]["templateId"] == "TPL_P" and msg["kakaoOptions"]["variables"]["#{송장번호}"] == "512345678901"
    # 같은 파일을 또 올리면 '이미등록'
    p2 = full_ctx.services["tracking"].preview("송장.xlsx", data, "CJ대한통운")
    assert p2.rows[0].status == "이미등록"


def test_tracking_match_by_name_and_phone(full_ctx):
    a = _order(full_ctx, cid="C0001")
    data = _xlsx([["수하인명", "수하인전화", "송장번호"], ["김사장", "010-1234-5678", "999888777666"]])
    p = full_ctx.services["tracking"].preview("logen.xlsx", data, "로젠택배")
    assert p.rows[0].status == "매칭" and p.rows[0].order_id == a.order_id

    _order(full_ctx, cid="C0001")  # 같은 사람 주문이 둘이면 사람에게 묻는다
    p = full_ctx.services["tracking"].preview("logen.xlsx", data, "로젠택배")
    assert p.rows[0].status == "확인필요" and len(p.rows[0].candidates) == 2
    r = full_ctx.services["tracking"].confirm(p.import_id, TrackingConfirmIn(carrier="로젠택배", picks={p.rows[0].row_no: a.order_id}))
    assert r.registered == 1


def test_password_protected_excel_message(full_ctx):
    with pytest.raises(ValidationFailed, match="비밀번호"):
        full_ctx.services["tracking"].preview("a.xlsx", b"\xd0\xcf\x11\xe0" + b"0" * 100, "CJ대한통운")


def test_truck_info_ships_and_sends_truck_template(full_ctx, http):
    o = _order(full_ctx, cid="C0002", items=(("CHI-10KG", 10),))
    assert o.ship_method == "화물"
    out = full_ctx.services["tracking"].set_truck(o.order_id, TruckIn(truck_no="경기12가3456", driver_phone="010-9999-0000"))
    assert out.status == "출고완료"
    msg = http.by("api.solapi.com")[0]["json"]["messages"][0]
    assert msg["kakaoOptions"]["templateId"] == "TPL_T"
    assert msg["kakaoOptions"]["variables"]["#{차량번호}"] == "경기12가3456"


def test_ship_without_tracking_waits_then_sends(full_ctx, http):
    o = _order(full_ctx)
    full_ctx.orders.ship(o.order_id)
    assert not http.by("api.solapi.com")  # 송장 없으면 기다림
    full_ctx.services["tracking"].set_tracking(o.order_id, TrackingIn(carrier="한진택배", tracking_no="1234-5678"))
    assert len(http.by("api.solapi.com")) == 1
    full_ctx.services["tracking"].set_tracking(o.order_id, TrackingIn(carrier="한진택배", tracking_no="1234-5678"))
    assert len(http.by("api.solapi.com")) == 1  # 두 번 보내지 않음
    assert full_ctx.services["notify"].notify_shipment(full_ctx.orders.get(o.order_id, fresh=True), force=True).sent
    assert len(http.by("api.solapi.com")) == 2


def test_notify_respects_customer_opt_out_and_logs(full_ctx, http):
    full_ctx.customers.update(("C0001",), {"notify_opt_in": False})
    o = _order(full_ctx)
    r = full_ctx.services["tracking"].set_tracking(o.order_id, TrackingIn(carrier="CJ대한통운", tracking_no="111122223333"))
    assert r.status == "출고완료" and not http.by("api.solapi.com")
    preview = full_ctx.services["notify"].preview(r)
    assert "111122223333" in preview.preview and "[예시공장]" in preview.preview


def test_notify_failure_is_logged_not_raised(full_ctx, http):
    http.queue("api.solapi.com", 200, {"failedMessageList": [{"statusMessage": "카카오톡 미사용자"}]})
    o = _order(full_ctx)
    full_ctx.services["tracking"].set_tracking(o.order_id, TrackingIn(carrier="CJ대한통운", tracking_no="111122223333"))
    logs = full_ctx.messages.recent(5, o.order_id)
    assert logs[0]["result"] == "실패" and "미사용자" in logs[0]["error"]
    assert full_ctx.orders.get(o.order_id, fresh=True).notified_at is None


# ---------------------------------------------------------------- 오픈마켓
SMARTSTORE_HEAD = ["상품주문번호", "주문번호", "수취인명", "수취인연락처1", "통합배송지", "우편번호", "상품명", "옵션정보", "수량", "배송메세지"]


def test_marketplace_import_and_remember_mapping(full_ctx):
    data = _xlsx([
        SMARTSTORE_HEAD,
        ["P1", "2026111900001", "홍길동", "010-5555-6666", "서울시 마포구 월드컵로 1", 3955, "국산 참기름 1.8L 업소용", "", 1, "문앞"],
        ["P2", "2026111900001", "홍길동", "010-5555-6666", "서울시 마포구 월드컵로 1", 3955, "국산 고춧가루", "용량: 5kg", 2, "문앞"],
        ["P3", "2026111900002", "이영희", "010-7777-8888", "부산시 해운대구 우동 2", 48000, "참기름 2병 세트", "", 1, ""],
    ])
    svc = full_ctx.services["marketplace"]
    p = svc.preview("스마트스토어.xlsx", data)
    assert p.adapter == "smartstore" and len(p.orders) == 2 and p.ready == 2
    first = p.orders[0]
    assert first.recipient == "홍길동" and first.zipcode == "03955" and len(first.lines) == 2
    assert first.lines[0].sku == "SES-18L"  # 이름 유사도 추천
    assert set(p.unmapped_names) == {"국산 참기름 1.8L 업소용", "국산 고춧가루 / 용량: 5kg", "참기름 2병 세트"}

    r = svc.confirm(p.preview_id, MarketConfirmIn(mappings={
        "국산 참기름 1.8L 업소용": MappingIn(sku="SES-18L"),
        "국산 고춧가루 / 용량: 5kg": MappingIn(sku="CHI-5KG"),
        "참기름 2병 세트": MappingIn(sku="SES-18L", multiplier=2),
    }))
    assert r.created == 2 and not r.errors
    o2 = full_ctx.orders.get(r.order_ids[1])
    assert o2.source == "스마트스토어" and o2.lines[0].qty == 2 and o2.ext_order_no == "smartstore:2026111900002"
    assert o2.customer_id == "" and o2.recipient == "이영희"

    # 같은 파일 다시 → 이미등록, 매핑은 기억됨
    p = svc.preview("스마트스토어.xlsx", data)
    assert p.duplicates == 2 and p.ready == 0
    assert all(l.mapped for o in p.orders for l in o.lines)
    assert len(svc.mappings()) == 3


def test_coupang_detected_and_missing_mapping_reported(full_ctx):
    data = _xlsx([
        ["번호", "묶음배송번호", "주문번호", "등록상품명", "등록옵션명", "구매수(수량)", "수취인이름", "수취인전화번호", "우편번호", "수취인 주소", "배송메세지"],
        [1, "B1", "300001", "모르는 상품", "", 3, "박민수", "010-1111-2222", "12345", "인천시 OO구", ""],
    ])
    svc = full_ctx.services["marketplace"]
    p = svc.preview("coupang.xlsx", data)
    assert p.adapter == "coupang" and p.orders[0].lines[0].qty == 3
    r = svc.confirm(p.preview_id, MarketConfirmIn())
    assert r.created == 0 and r.errors and "모르는 상품" in r.errors[0]
