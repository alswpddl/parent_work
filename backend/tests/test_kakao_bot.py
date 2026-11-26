from __future__ import annotations

from types import SimpleNamespace

from app.integrations.claude_client import ClaudeClient
from app.schemas.settings import SettingsPatch


def _ask(ctx, text, user="u1"):
    return ctx.services["kakao_bot"].answer({"userRequest": {"utterance": text, "user": {"id": user}}})


def _texts(r):
    out = []
    for o in r["template"]["outputs"]:
        if "simpleText" in o:
            out.append(o["simpleText"]["text"])
        if "textCard" in o:
            out.append(o["textCard"]["title"] + " " + o["textCard"]["description"])
    return "\n".join(out)


def _setup(ctx):
    ctx.settings.save(SettingsPatch(shop_shipping_fee=4000, shop_free_shipping_over=50000, shop_intro="통영에서 30년"))


def test_response_shape_and_quick_replies(full_ctx):
    r = _ask(full_ctx, "안녕하세요")
    assert r["version"] == "2.0" and 1 <= len(r["template"]["outputs"]) <= 3
    labels = [q["label"] for q in r["template"]["quickReplies"]]
    assert "주문하기" in labels and len(labels) <= 10 and all(len(l) <= 14 for l in labels)
    assert "안녕하세요" in _texts(r)


def test_rule_answers(full_ctx):
    _setup(full_ctx)
    assert "4,000원" in _texts(_ask(full_ctx, "택배비 얼마예요?")) and "50,000원" in _texts(_ask(full_ctx, "택배비"))
    assert "농협" in _texts(_ask(full_ctx, "입금 계좌 알려주세요"))
    assert "일요일" in _texts(_ask(full_ctx, "언제 받을 수 있어요?"))
    r = _ask(full_ctx, "상품·가격")
    assert "참기름" in _texts(r) and "38,000원" in _texts(r)
    btn = r["template"]["outputs"][1]["textCard"]["buttons"][0]
    assert btn["action"] == "webLink" and btn["webLinkUrl"].endswith("/shop")
    r = _ask(full_ctx, "주문하기")
    assert any(b["action"] == "webLink" for b in r["template"]["outputs"][0]["textCard"]["buttons"])
    r = _ask(full_ctx, "전화 연결")
    assert r["template"]["outputs"][0]["textCard"]["buttons"][0]["action"] == "phone"


def test_product_name_and_alias(full_ctx):
    full_ctx.products.update(("CHI-5KG",), {"aliases": "고추가루, 고춧가루 작은거"})
    t = _texts(_ask(full_ctx, "고추가루 있어요?"))
    assert "고춧가루" in t and "참기름" not in t
    r = _ask(full_ctx, "참기름 얼마예요")  # '가격' 질문이어도 그 상품만
    assert "참기름" in _texts(r) and "고춧가루" not in _texts(r)
    assert "/shop/item/" in r["template"]["outputs"][1]["textCard"]["buttons"][0]["webLinkUrl"]


def test_order_lookup(full_ctx):
    from app.modules.q2_web_order.service import GuestOrderIn
    from app.schemas.order import OrderItemIn

    out = full_ctx.services["web_order"].place(GuestOrderIn(
        name="김영희", phone="010-7777-8888", address="서울시 마포구 1", items=[OrderItemIn(sku="SES-18L", qty=1)], agree_privacy=True,
    ), "1.1.1.1")
    assert "뒤 4자리" in _texts(_ask(full_ctx, "주문 조회"))
    t = _texts(_ask(full_ctx, f"{out.order_id.lower()} 8888"))
    assert out.order_id in t and "준비 중" in t
    assert "찾지 못했어요" in _texts(_ask(full_ctx, f"{out.order_id} 1234"))


def test_free_question_uses_ai_or_logs(full_ctx):
    t = _texts(_ask(full_ctx, "보관은 어떻게 해요?"))  # AI 없음 → 전화 안내 + 기록
    assert "잘 못 알아들었어요" in t
    assert any(r.get("action") == "챗봇 질문" for r in full_ctx.logs.rows(fresh=True))

    calls = {}

    class FakeMessages:
        def create(self, **kw):
            calls.update(kw)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="냉장 보관해 주세요 🙂")])

    full_ctx.claude = ClaudeClient("", "m", client=SimpleNamespace(messages=FakeMessages()))
    assert "냉장 보관" in _texts(_ask(full_ctx, "보관은 어떻게 해요?"))
    assert "참기름" in calls["system"] and "지어내지" in calls["system"]  # 공장 정보만 보고 답하게


def test_ai_failure_falls_back(full_ctx):
    class Boom:
        def create(self, **kw):
            raise TimeoutError("slow")

    full_ctx.claude = ClaudeClient("", "m", client=SimpleNamespace(messages=Boom()))
    assert "잘 못 알아들었어요" in _texts(_ask(full_ctx, "보관은 어떻게 해요?"))
