from __future__ import annotations

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


def _menu(r):
    cards = [o["listCard"] for o in r["template"]["outputs"] if "listCard" in o]
    return cards[0] if cards else None


def test_greeting_shows_vertical_menu(full_ctx):
    r = _ask(full_ctx, "안녕하세요")
    assert r["version"] == "2.0" and 1 <= len(r["template"]["outputs"]) <= 3
    m = _menu(r)
    titles = [i["title"] for i in m["items"]]
    assert titles == ["상품·가격", "주문하기", "택배비", "받는 날", "입금 계좌"] and len(m["buttons"]) <= 2
    assert "주문 조회" not in titles
    assert all(i["action"] == "message" for i in m["items"])
    assert "quickReplies" not in r["template"]  # 옆으로 긴 빠른 답장 없음
    assert "안녕하세요" in _texts(r)
    # 다른 답변 아래엔 [메뉴 보기] 하나만
    r = _ask(full_ctx, "택배비")
    assert [q["label"] for q in r["template"]["quickReplies"]] == ["메뉴 보기"]
    assert _menu(_ask(full_ctx, "메뉴 보기"))


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


def test_no_order_lookup_in_chat(full_ctx):
    """주문 조회는 챗봇에서 안 함 — 글로 보내면 메뉴로"""
    r = _ask(full_ctx, "20261126-K7Q3 8888")
    assert _menu(r) and "글로 답해 드리지 않아요" in _texts(r)


def test_unknown_question_gets_menu_and_is_logged(full_ctx):
    r = _ask(full_ctx, "보관은 어떻게 해요?")
    assert "글로 답해 드리지 않아요" in _texts(r) and "메뉴에서 골라" in _texts(r)
    assert _menu(r)["items"][0]["title"] == "상품·가격"
    assert any(x.get("action") == "챗봇 질문" and "보관" in x.get("detail", "") for x in full_ctx.logs.rows(fresh=True))


def test_never_calls_ai(full_ctx):
    from types import SimpleNamespace

    from app.integrations.claude_client import ClaudeClient

    class Boom:
        def create(self, **kw):
            raise AssertionError("챗봇은 AI 를 부르면 안 돼요")

    full_ctx.claude = ClaudeClient("", "m", client=SimpleNamespace(messages=Boom()))
    assert "글로 답해 드리지 않아요" in _texts(_ask(full_ctx, "보관은 어떻게 해요?"))
