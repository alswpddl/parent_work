from __future__ import annotations

from datetime import date

from app.integrations.claude_client import ClaudeClient
from app.modules.q1_orders.parser import parse_order_text, parse_with_rules, resolve_due_date
from app.services.matching import match_customer, match_product, normalize

from .conftest import BASE_DAY

SAMPLE = """안녕하세요 사장님~ 한솥식당입니다
참기름 1.8L 10개, 들기름 1.8리터 5통
고춧가루 5키로 2개 부탁드려요
금요일까지 받을 수 있을까요? 오전에 와주세요"""


def test_normalize():
    assert normalize("1.8 리터") == "1.8l"
    assert normalize("5 키로") == "5kg"
    assert normalize("한솥 사장님") == "한솥"


def test_rule_parser_sample(ctx):
    customers, products = ctx.customers.list(), ctx.products.list()
    p = parse_with_rules(SAMPLE, customers, products, BASE_DAY)
    assert p.customer_id == "C0001"
    got = {i.sku: i.qty for i in p.items}
    assert got == {"SES-18L": 10, "PER-18L": 5, "CHI-5KG": 2}
    assert p.due_date == date(2026, 11, 20)  # 금요일
    assert "오전" in p.note
    assert p.address == ""  # 주소가 없는 메시지에서 엉뚱한 줄을 주소로 잡지 않음


def test_rule_parser_ambiguous_spec_without_name(ctx):
    p = parse_with_rules("행복마트\n1.8L 20개", ctx.customers.list(), ctx.products.list(), BASE_DAY)
    assert p.customer_id == "C0002"
    assert len(p.items) == 1 and p.items[0].sku is None and p.items[0].qty == 20  # 참기름/들기름 중 사람이 고름


def test_rule_parser_address_phone(ctx):
    text = "한솥\n고춧가루 10kg 3개\n주소: 서울시 마포구 월드컵로 12-3\n받는분 010 5555 6666"
    p = parse_with_rules(text, ctx.customers.list(), ctx.products.list(), BASE_DAY)
    assert p.items[0].sku == "CHI-10KG" and p.items[0].qty == 3
    assert p.address == "서울시 마포구 월드컵로 12-3"
    assert p.phone == "010-5555-6666"


def test_due_date_rules():
    assert resolve_due_date("내일 주세요", BASE_DAY) == date(2026, 11, 19)
    assert resolve_due_date("11/25 까지", BASE_DAY) == date(2026, 11, 25)
    assert resolve_due_date("12월 3일 오전", BASE_DAY) == date(2026, 12, 3)
    assert resolve_due_date("참기름 1.8L 10개", BASE_DAY) is None  # 규격을 날짜로 오인하지 않음
    assert resolve_due_date("다음주 화요일", BASE_DAY) == date(2026, 12, 1)
    assert resolve_due_date("1/5", date(2026, 12, 20)) == date(2027, 1, 5)


def test_match_customer_alias(ctx):
    best, cands = match_customer("한솥 사장님", ctx.customers.list())
    assert best and best.customer_id == "C0001"


def test_match_product_requires_same_spec(ctx):
    best, _ = match_product("고춧가루", ctx.products.list(), spec="10kg")
    assert best and best.sku == "CHI-10KG"
    best, cands = match_product("고춧가루", ctx.products.list())
    assert best is None and len(cands) == 2  # 5kg / 10kg 중 고르게 함


def test_ai_parser_used_when_available(ctx, fake_anthropic):
    sdk, msgs = fake_anthropic(
        {
            "customer_id": "C0001",
            "customer_name": "한솥식당",
            "items": [{"sku": "SES-18L", "raw_name": "참기름 큰거", "spec": "1.8L", "qty": 12}],
            "address": "",
            "due_date": "2026-11-20",
            "note": "오전 배송",
        }
    )
    client = ClaudeClient("", "claude-haiku-5-5", client=sdk)
    parsed, parser, warnings = parse_order_text("아무 메시지", ctx.customers.list(), ctx.products.list(), client, day=BASE_DAY)
    assert parser == "ai" and warnings == []
    assert parsed.items[0].qty == 12 and parsed.due_date == date(2026, 11, 20)
    call = msgs.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "record_order"}
    assert "<customers>" in call["messages"][0]["content"] and "한솥식당" in call["messages"][0]["content"]


def test_ai_parser_retries_with_auto_on_400(ctx, fake_anthropic):
    sdk, msgs = fake_anthropic({"customer_name": "", "items": [], "address": "", "due_date": "", "note": ""}, fail_forced_with=400)
    client = ClaudeClient("", "claude-sonnet-5-5", client=sdk)
    _, parser, _ = parse_order_text("x", [], [], client, day=BASE_DAY)
    assert parser == "ai"
    assert [c["tool_choice"]["type"] for c in msgs.calls] == ["tool", "auto"]


def test_ai_failure_falls_back_to_rules(ctx, fake_anthropic):
    sdk, _ = fake_anthropic(fail_forced_with=500)
    client = ClaudeClient("", "claude-haiku-5-5", client=sdk)
    parsed, parser, warnings = parse_order_text(SAMPLE, ctx.customers.list(), ctx.products.list(), client, day=BASE_DAY)
    assert parser == "rule" and warnings
    assert len(parsed.items) == 3
