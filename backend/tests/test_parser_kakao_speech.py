"""카톡 말투 그대로 붙여넣어도 품목·수량을 읽는지 (가염식품 멸치액젓 3종 기준)"""
import pytest

from app.modules.q1_orders.parser import parse_with_rules, plain_korean
from app.schemas.product import ProductOut

P = [
    ProductOut.from_row(d)
    for d in [
        dict(sku="S", name="멸치액젓", spec="1.8kg", aliases="액젓, 액젓 1.8", unit="통", unit_kg=2, active=True),
        dict(sku="M", name="멸치액젓", spec="5kg", aliases="액젓 5키로", unit="통", unit_kg=5.4, active=True),
        dict(sku="L", name="멸치액젓", spec="20kg", aliases="말통, 액젓 말통", unit="통", unit_kg=21, active=True),
    ]
]


@pytest.mark.parametrize(
    "text,want",
    [
        ("액젓 20키로 2통 보내주세요", {"L": 2}),
        ("멸치액젓 5키로 3개, 1.8 10개", {"M": 3, "S": 10}),
        ("액젓 말통 2개요", {"L": 2}),
        ("액젓 1.8리터 5병", {"S": 5}),
        ("멸치액젓 이십키로 두통", {"L": 2}),
        ("액젓 20짜리 하나", {"L": 1}),
        ("액젓 오키로 세 통", {"M": 3}),
        ("말통 하나랑 5키로 두통", {"L": 1, "M": 2}),
        ("액젓 5키로2 말통1", {"M": 2, "L": 1}),
    ],
)
def test_kakao_speech(text, want):
    got = {i.sku: i.qty for i in parse_with_rules(text, [], P).items if i.sku}
    assert got == want


def test_plain_korean_keeps_names():
    assert plain_korean("한솥 두 통") == "한솥 2통"
    assert plain_korean("세븐 일레븐") == "세븐 일레븐"
