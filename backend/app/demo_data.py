"""메모리 모드(구글 시트 연결 전)에서 바로 눌러볼 수 있는 예시 데이터 — 젓갈 공장 기준.

- 품목 6개 (새우젓·명란젓·오징어젓·낙지젓·멸치액젓, 자재 매핑 포함)
- 거래처 3곳, 자재 10종, 공장 설정
- 지난 두 달치 출고 완료 주문 (→ 월말 정산·리마인드 화면이 비어 있지 않게)
- 출고 대기 주문 3건 (웹 주문서 1건 포함)

실제 품목·가격·무게는 구글 시트 '품목' 탭에서 바꾸면 된다. (과세구분은 세무사 확인 후 입력)
"""

from __future__ import annotations

from datetime import timedelta

from .core.repository import Repository
from .core.sheet_schema import INVENTORY
from .core.timeutil import now, today
from .schemas.order import OrderCreate, OrderItemIn
from .schemas.settings import SettingsPatch


def seed_demo(ctx) -> None:
    seed_basics(ctx)
    seed_history(ctx)


def _p(sku, name, spec, unit, kg, upb, price, container, box, label, aliases="", desc=""):
    return {
        "sku": sku, "name": name, "spec": spec, "aliases": aliases, "unit": unit, "unit_kg": kg,
        "units_per_box": upb, "unit_price": price, "retail_price": round(price * 1.25, -3),  # 예시: 개인판매가
        "description": desc, "shop_visible": True,
        "container_item": container, "box_item": box, "label_item": label, "active": True,
    }


def seed_basics(ctx) -> None:
    ctx.products.insert_many(
        [
            _p("SAE-1K", "새우젓(추젓)", "1kg", "통", 1.15, 12, 18000, "CT-1K", "BOX-12", "LBL-SAE",
               "새우젓, 추젓, 새우젓 1키로", "가을 추젓으로 담근 새우젓. 김장·찌개용"),
            _p("SAE-5K", "새우젓(추젓)", "5kg", "통", 5.4, 2, 80000, "CT-5K", "BOX-2", "LBL-SAE",
               "새우젓 5키로, 추젓 5키로, 새우젓 큰통", "업소·김장용 대용량"),
            _p("MYE-500", "명란젓", "500g", "통", 0.6, 20, 22000, "CT-500", "BOX-20", "LBL-MYE",
               "명란, 명란젓갈", "저염 명란젓"),
            _p("OJI-1K", "오징어젓", "1kg", "통", 1.15, 12, 15000, "CT-1K", "BOX-12", "LBL-OJI",
               "오징어젓갈, 오징어", "반찬용 오징어젓"),
            _p("NAK-1K", "낙지젓", "1kg", "통", 1.15, 12, 25000, "CT-1K", "BOX-12", "LBL-NAK",
               "낙지젓갈, 낙지", "매콤한 낙지젓"),
            _p("AEK-9K", "멸치액젓", "9kg", "말통", 9.6, None, 30000, "CT-9K", "", "LBL-AEK",
               "액젓, 멸치액젓 말통, 액젓 한말", "김장용 멸치액젓 한 말"),
        ]
    )
    ctx.customers.insert_many(
        [
            {"customer_id": "C0001", "name": "바다식당", "aliases": "바다, 바다식당 사장님", "type": "B2B",
             "contact_name": "김사장", "phone": "010-1234-5678", "address": "부산시 OO구 OO로 45 1층",
             "zipcode": "48000", "default_method": "자동", "email": "sea@example.com", "biz_no": "123-45-67890",
             "owner_name": "김바다", "notify_opt_in": True, "active": True},
            {"customer_id": "C0002", "name": "행복마트", "aliases": "행복", "type": "B2B",
             "contact_name": "박실장", "phone": "010-2222-3333", "address": "경남 OO시 OO길 7 물류창고",
             "zipcode": "51000", "default_method": "화물", "email": "", "biz_no": "222-33-44444",
             "owner_name": "이행복", "notify_opt_in": True, "active": True},
        ]
    )
    inv: Repository[dict] = Repository(ctx.sheets, INVENTORY)
    ts = now()
    item = lambda iid, cat, name, unit, stock, safety, reorder, sup: {  # noqa: E731
        "item_id": iid, "category": cat, "name": name, "unit": unit, "stock": stock, "safety_stock": safety,
        "reorder_qty": reorder, "supplier": sup, "updated_at": ts,
    }
    inv.insert_many(
        [
            item("CT-500", "용기", "500g 통", "개", 300, 150, 1000, "OO용기"),
            item("CT-1K", "용기", "1kg 통", "개", 650, 400, 2000, "OO용기"),
            item("CT-5K", "용기", "5kg 통", "개", 60, 40, 200, "OO용기"),
            item("CT-9K", "용기", "9kg 말통", "개", 25, 30, 100, "OO용기"),
            item("BOX-12", "박스", "1kg×12 박스", "개", 120, 50, 300, "OO박스"),
            item("BOX-20", "박스", "500g×20 박스", "개", 40, 20, 100, "OO박스"),
            item("BOX-2", "박스", "5kg×2 박스", "개", 50, 30, 150, "OO박스"),
            item("LBL-SAE", "라벨", "새우젓 라벨", "장", 1500, 800, 3000, "OO인쇄"),
            item("LBL-MYE", "라벨", "명란젓 라벨", "장", 400, 500, 2000, "OO인쇄"),
            item("LBL-OJI", "라벨", "오징어젓 라벨", "장", 900, 500, 2000, "OO인쇄"),
            item("LBL-NAK", "라벨", "낙지젓 라벨", "장", 700, 500, 2000, "OO인쇄"),
            item("LBL-AEK", "라벨", "멸치액젓 라벨", "장", 300, 200, 1000, "OO인쇄"),
        ]
    )
    ctx.settings.save(
        SettingsPatch(
            factory_name="예시젓갈", factory_address="경남 통영시 OO로 123", factory_phone="055-000-0000",
            company_biz_no="111-22-33333", company_owner="홍길동", bank_account="농협 000-0000-0000-00 홍길동",
            self_order_notice="오후 2시 전 주문은 다음 날 출고돼요.",
            shop_notice="오후 2시 전 주문은 다음 날 출고돼요. 입금 확인 후 보내 드려요.",
            shop_shipping_fee=4000, shop_free_shipping_over=50000,
        )
    )


def seed_history(ctx) -> None:
    """지난 주문 기록과 출고 대기 주문 (화면 둘러보기용)."""
    ctx.customers.insert(
        {"customer_id": "C0003", "name": "시골반찬", "aliases": "", "type": "B2B", "contact_name": "최이모",
         "phone": "010-4444-5555", "address": "경남 OO군 OO면 OO리 12", "zipcode": "52000",
         "default_method": "택배", "active": True}
    )
    history = [
        ("C0001", 50, [("SAE-1K", 6), ("MYE-500", 4)]),
        ("C0001", 43, [("SAE-1K", 6)]),
        ("C0001", 36, [("SAE-1K", 6), ("OJI-1K", 6)]),
        ("C0001", 29, [("SAE-1K", 12)]),
        ("C0001", 22, [("SAE-1K", 6), ("NAK-1K", 3)]),
        ("C0002", 60, [("AEK-9K", 10), ("SAE-5K", 4)]),
        ("C0002", 46, [("AEK-9K", 8)]),
        ("C0002", 32, [("AEK-9K", 10), ("SAE-5K", 6)]),
        ("C0002", 18, [("AEK-9K", 12)]),
        ("C0003", 40, [("OJI-1K", 2)]),
        ("C0003", 12, [("OJI-1K", 3)]),
    ]
    t0 = now()
    for cid, ago, items in history:
        o = ctx.orders.create(OrderCreate(customer_id=cid, items=[OrderItemIn(sku=s, qty=q) for s, q in items]), actor="예시")
        created = t0 - timedelta(days=ago)
        fields = {
            "order_id": f"O-{created:%Y%m%d}-001",
            "created_at": created, "updated_at": created, "due_date": (created + timedelta(days=2)).date(),
            "status": "출고완료", "shipped_at": created + timedelta(days=1),
        }
        if o.ship_method == "택배":
            fields.update({"carrier": "CJ대한통운", "tracking_no": f"5{ago:03d}12345678"})
        else:
            fields.update({"truck_no": "경남12가3456", "driver_phone": "010-9999-0000"})
        ctx.orders_repo.update_many([((o.order_id, l.line_no), fields) for l in o.lines])

    # --- 출고 대기 주문 ---
    ctx.orders.create(OrderCreate(customer_id="C0003", items=[OrderItemIn(sku="OJI-1K", qty=3), OrderItemIn(sku="NAK-1K", qty=2)],
                                  due_date=today() + timedelta(days=1), note="오전 배송 부탁"), actor="예시")
    ctx.orders.create(OrderCreate(customer_id="C0002", items=[OrderItemIn(sku="AEK-9K", qty=10)],
                                  due_date=today() + timedelta(days=2)), actor="예시")
    ctx.orders.create(OrderCreate(customer_name="김영희", recipient="김영희", phone="010-7777-8888",
                                  address="서울시 OO구 OO로 9 101동 202호", items=[OrderItemIn(sku="MYE-500", qty=2), OrderItemIn(sku="SAE-1K", qty=1)],
                                  due_date=today() + timedelta(days=1), source="웹주문서"), actor="예시")
