from __future__ import annotations

from app.config import ALL_MODULES, AppConfig
from app.context import bootstrap, build_context
from app.core.sheets import MemoryBackend
from app.core.timeutil import today
from app.integrations.claude_client import ClaudeClient
from app.modules import load_modules, register_without_app
from app.modules.q1_orders.parser import parse_with_rules
from app.modules.q4_settlement.service import GenerateIn, prev_period


def _demo_ctx():
    cfg = AppConfig(app_env="test", sheets_backend="memory", sheets_cache_ttl=0, seed_demo_data=True)
    c = build_context(cfg, backend=MemoryBackend(), claude=ClaudeClient("", "m"))
    register_without_app(load_modules(ALL_MODULES), c)
    bootstrap(c)  # 메모리 모드 + seed_demo_data → 젓갈 예시 데이터 전체
    return c


def test_full_demo_data_drives_every_screen():
    c = _demo_ctx()
    assert {p.name for p in c.products.list()} >= {"새우젓(추젓)", "명란젓", "멸치액젓"}
    board = c.orders.query(statuses=["접수", "출고대기"])
    assert {o.ship_method for o in board} == {"택배", "화물"}
    assert any(o.source == "웹주문서" for o in board)
    assert [s.customer_id for s in c.services["reorder"].reminders()] == ["C0001"]
    r = c.services["settlement"].generate(GenerateIn(period=prev_period(today())))
    assert len(r.settlements) >= 2
    text = c.services["briefing"].preview().text
    assert "주문할 때 된 거래처" in text and "자재 재고" in text
    assert c.services["web_order"].info().products


def test_rule_parser_handles_jeotgal_messages():
    c = _demo_ctx()
    msg = "바다식당입니다\n새우젓 1키로 10통, 명란 500g 4개\n액젓 9kg 2말 금요일까지요"
    p = parse_with_rules(msg, c.customers.list(), c.products.list())
    assert p.customer_id == "C0001"
    assert {i.sku: i.qty for i in p.items} == {"SAE-1K": 10, "MYE-500": 4, "AEK-9K": 2}
