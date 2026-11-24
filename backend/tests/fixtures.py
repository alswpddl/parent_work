"""테스트 전용 고정 데이터.

앱의 예시 데이터(app/demo_data.py)는 실제 공장 품목에 맞춰 바뀔 수 있으므로,
테스트는 바뀌지 않는 이 데이터로 돌린다.
"""

from __future__ import annotations

from app.core.timeutil import now
from app.schemas.settings import SettingsPatch


def seed_test_basics(ctx) -> None:
    """테스트 고정 데이터: 품목 4개·거래처 2곳·자재 9종·설정. (앱 예시 데이터와 따로 둔다)"""
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
    from app.core.repository import Repository
    from app.core.sheet_schema import INVENTORY

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
