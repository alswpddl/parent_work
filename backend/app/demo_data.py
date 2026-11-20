"""메모리 모드(구글 시트 연결 전)에서 바로 눌러볼 수 있는 예시 데이터.

- 품목 4개 (자재 매핑·과세구분 포함), 거래처 3곳, 자재 8종
- 지난 두 달치 출고 완료 주문 (→ 월말 정산·리마인드 화면이 비어 있지 않게)
- 출고 대기 주문 2건 (택배 1, 화물 1)
"""

from __future__ import annotations

from datetime import timedelta

from .core.timeutil import now, today
from .schemas.order import OrderCreate, OrderItemIn
from .schemas.settings import SettingsPatch


def seed_demo(ctx) -> None:
    seed_basics(ctx)
    seed_history(ctx)


def seed_basics(ctx) -> None:
    """품목·거래처 2곳·자재·설정 (테스트에서도 이것만 쓴다)."""
    ctx.products.insert_many(
        [
            {"sku": "SES-18L", "name": "참기름", "spec": "1.8L", "aliases": "참기름 큰거", "unit": "통", "unit_kg": 1.9,
             "units_per_box": 6, "unit_price": 38000, "tax_type": "과세", "container_item": "CT-18L",
             "box_item": "BOX-6", "label_item": "LBL-SES", "active": True},
            {"sku": "PER-18L", "name": "들기름", "spec": "1.8L", "aliases": "들기름 큰거", "unit": "통", "unit_kg": 1.9,
             "units_per_box": 6, "unit_price": 42000, "tax_type": "과세", "container_item": "CT-18L",
             "box_item": "BOX-6", "label_item": "LBL-PER", "active": True},
            {"sku": "CHI-5KG", "name": "고춧가루", "spec": "5kg", "aliases": "고추가루 5키로", "unit": "봉", "unit_kg": 5.2,
             "units_per_box": 2, "unit_price": 95000, "tax_type": "면세", "container_item": "BAG-5KG",
             "box_item": "BOX-2", "label_item": "LBL-CHI", "active": True},
            {"sku": "CHI-10KG", "name": "고춧가루", "spec": "10kg", "aliases": "고추가루 10키로", "unit": "봉", "unit_kg": 10.3,
             "units_per_box": 1, "unit_price": 185000, "tax_type": "면세", "container_item": "BAG-10KG",
             "box_item": "BOX-1", "label_item": "LBL-CHI", "active": True},
        ]
    )
    ctx.customers.insert_many(
        [
            {"customer_id": "C0001", "name": "한솥식당", "aliases": "한솥, 한솥 사장님", "type": "B2B",
             "contact_name": "김사장", "phone": "010-1234-5678", "address": "서울시 OO구 OO로 45 1층",
             "zipcode": "01234", "default_method": "자동", "email": "hansot@example.com", "biz_no": "123-45-67890",
             "owner_name": "김한솥", "notify_opt_in": True, "active": True},
            {"customer_id": "C0002", "name": "행복마트", "aliases": "행복", "type": "B2B",
             "contact_name": "박실장", "phone": "010-2222-3333", "address": "경기도 OO시 OO길 7 물류창고",
             "zipcode": "04567", "default_method": "화물", "email": "", "biz_no": "222-33-44444",
             "owner_name": "이행복", "notify_opt_in": True, "active": True},
        ]
    )
    from .core.repository import Repository
    from .core.sheet_schema import INVENTORY

    inv: Repository[dict] = Repository(ctx.sheets, INVENTORY)
    ts = now()
    inv.insert_many(
        [
            {"item_id": "CT-18L", "category": "용기", "name": "1.8L 기름통", "unit": "개", "stock": 420, "safety_stock": 300, "reorder_qty": 1000, "supplier": "OO용기", "supplier_phone": "031-111-2222", "updated_at": ts},
            {"item_id": "BAG-5KG", "category": "용기", "name": "5kg 포장봉투", "unit": "장", "stock": 80, "safety_stock": 50, "reorder_qty": 300, "supplier": "OO포장", "updated_at": ts},
            {"item_id": "BAG-10KG", "category": "용기", "name": "10kg 포장봉투", "unit": "장", "stock": 30, "safety_stock": 40, "reorder_qty": 200, "supplier": "OO포장", "updated_at": ts},
            {"item_id": "BOX-6", "category": "박스", "name": "6입 박스", "unit": "개", "stock": 120, "safety_stock": 60, "reorder_qty": 300, "supplier": "OO박스", "updated_at": ts},
            {"item_id": "BOX-2", "category": "박스", "name": "2입 박스", "unit": "개", "stock": 70, "safety_stock": 40, "reorder_qty": 200, "supplier": "OO박스", "updated_at": ts},
            {"item_id": "BOX-1", "category": "박스", "name": "1입 박스", "unit": "개", "stock": 50, "safety_stock": 30, "reorder_qty": 200, "supplier": "OO박스", "updated_at": ts},
            {"item_id": "LBL-SES", "category": "라벨", "name": "참기름 라벨", "unit": "장", "stock": 900, "safety_stock": 500, "reorder_qty": 2000, "supplier": "OO인쇄", "updated_at": ts},
            {"item_id": "LBL-PER", "category": "라벨", "name": "들기름 라벨", "unit": "장", "stock": 350, "safety_stock": 500, "reorder_qty": 2000, "supplier": "OO인쇄", "updated_at": ts},
            {"item_id": "LBL-CHI", "category": "라벨", "name": "고춧가루 라벨", "unit": "장", "stock": 600, "safety_stock": 300, "reorder_qty": 1000, "supplier": "OO인쇄", "updated_at": ts},
        ]
    )
    ctx.settings.save(
        SettingsPatch(
            factory_name="예시공장", factory_address="경기도 OO시 OO로 123", factory_phone="031-000-0000",
            company_biz_no="111-22-33333", company_owner="홍길동", bank_account="농협 000-0000-0000-00 홍길동",
            self_order_notice="오후 3시 전 주문은 다음 날 출고돼요.",
        )
    )



def seed_history(ctx) -> None:
    """지난 주문 기록과 출고 대기 주문 (화면 둘러보기용)."""
    ctx.customers.insert(
        {"customer_id": "C0003", "name": "시골밥상", "aliases": "", "type": "B2B", "contact_name": "최이모",
         "phone": "010-4444-5555", "address": "충남 OO군 OO면 OO리 12", "zipcode": "32100",
         "default_method": "택배", "active": True}
    )
    # --- 지난 주문 기록 (출고 완료) ---
    history = [
        ("C0001", 50, [("SES-18L", 6), ("CHI-5KG", 2)]),
        ("C0001", 43, [("SES-18L", 6)]),
        ("C0001", 36, [("SES-18L", 6), ("PER-18L", 6)]),
        ("C0001", 29, [("SES-18L", 12)]),
        ("C0001", 22, [("SES-18L", 6), ("CHI-5KG", 2)]),
        ("C0002", 60, [("CHI-10KG", 10), ("SES-18L", 24)]),
        ("C0002", 46, [("CHI-10KG", 8)]),
        ("C0002", 32, [("CHI-10KG", 10), ("PER-18L", 12)]),
        ("C0002", 18, [("CHI-10KG", 12)]),
        ("C0003", 40, [("PER-18L", 2)]),
        ("C0003", 12, [("PER-18L", 3)]),
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
            fields.update({"truck_no": "경기12가3456", "driver_phone": "010-9999-0000"})
        ctx.orders_repo.update_many([((o.order_id, l.line_no), fields) for l in o.lines])

    # --- 출고 대기 주문 ---
    ctx.orders.create(OrderCreate(customer_id="C0003", items=[OrderItemIn(sku="SES-18L", qty=3), OrderItemIn(sku="PER-18L", qty=2)],
                                  due_date=today() + timedelta(days=1), note="오전 배송 부탁"), actor="예시")
    ctx.orders.create(OrderCreate(customer_id="C0002", items=[OrderItemIn(sku="CHI-10KG", qty=10)],
                                  due_date=today() + timedelta(days=2)), actor="예시")
