"""카카오톡 챗봇 답변 만들기.

정해진 질문에만 정해진 답을 한다 (AI 없음, 1:1 상담으로 넘기지 않음):
  상품·가격 · 상품 이름/별칭 · 주문하기 · 택배비 · 받는 날 · 입금 계좌 · 전화
메뉴는 위아래로 놓인 목록(listCard)으로 보여 준다 — 옆으로 길게 밀리는 빠른 답장 대신.
글로 직접 물으면 "아래 메뉴에서 골라 주세요" + 메뉴. 그 글은 _기록 탭에 '챗봇 질문'으로 남는다.
주문 조회는 챗봇에서 하지 않고 주문서 마이페이지·주문 조회 화면에서 한다.
"""

from __future__ import annotations

import re
from typing import Any

from ...core.errors import AppError
from ...core.timeutil import fmt_date_ko
from ...schemas.settings import WEEKDAYS_KO, closed_weekdays

# 세로 메뉴 (listCard 항목은 최대 5개) — (보이는 이름, 누르면 보내는 말, 한 줄 설명)
MENU: list[tuple[str, str, str]] = [
    ("상품·가격", "상품·가격", "어떤 젓갈이 있고 얼마인지"),
    ("주문하기", "주문하기", "주문서 열기"),
    ("택배비", "택배비", "택배비와 무료 기준"),
    ("받는 날", "받는 날", "주문하면 언제 받는지"),
    ("입금 계좌", "입금 계좌", "계좌로 입금할 때"),
]
MENU_WORDS = ("메뉴", "처음으로", "처음")

# 질문 종류 → 알아듣는 말 (앞에 있을수록 먼저)
INTENTS: list[tuple[str, tuple[str, ...]]] = [
    ("menu", MENU_WORDS),
    ("order", ("주문하기", "주문할", "주문 할", "주문하고", "사고 싶", "살게", "구매", "구입", "보내 주세요", "보내주세요", "주문서")),
    ("account", ("계좌", "입금", "송금", "이체", "통장")),
    ("shipping", ("택배비", "배송비", "배달비", "무료배송", "무료 배송", "택배")),
    ("due", ("받는 날", "언제 받", "며칠", "도착일", "배송일", "출고", "휴무", "쉬는 날", "주말")),
    ("phone", ("전화", "통화", "상담", "사장님", "사람")),
    ("products", ("상품", "가격", "얼마", "메뉴", "종류", "뭐 팔", "뭐팔", "품목", "판매")),
    ("hello", ("안녕", "처음", "시작", "도움", "help", "hi", "hello")),
]


def _quick(labels: list[str] | None = None) -> list[dict]:
    return [{"label": l, "action": "message", "messageText": l} for l in (labels or ["메뉴 보기"])][:10]


def menu_out(title: str, buttons: list[dict]) -> dict:
    """세로 메뉴 카드: 질문 5개가 위아래로, 아래에 전화·주문서 버튼"""
    return {"listCard": {
        "header": {"title": title[:50]},
        "items": [{"title": t, "description": d, "action": "message", "messageText": m} for t, m, d in MENU][:5],
        "buttons": buttons[:2],
    }}

def text_out(text: str) -> dict:
    return {"simpleText": {"text": text[:1000]}}


def card_out(title: str, desc: str, buttons: list[dict]) -> dict:
    return {"textCard": {"title": title[:50], "description": desc[:400], "buttons": buttons[:3]}}


def respond(*outputs: dict, quick: list[str] | None = None, menu: bool = False) -> dict:
    """답변 + 아래에 [메뉴 보기] 버튼 하나 (메뉴 자체를 보여 줄 땐 빠른 답장 없음)"""
    tpl: dict[str, Any] = {"outputs": list(outputs)[:3] or [text_out("…")]}
    if not menu:
        tpl["quickReplies"] = _quick(quick)
    return {"version": "2.0", "template": tpl}


class KakaoBot:
    def __init__(self, ctx: Any):
        self.ctx = ctx

    # ---------------------------------------------------------------- 진입
    def answer(self, payload: dict) -> dict:
        req = payload.get("userRequest") or {}
        text = str(req.get("utterance") or "").strip()
        user = str((req.get("user") or {}).get("id") or "")
        intent = self.classify(text)
        # 상품 이름이 나오면 (가격·주문 질문이어도) 그 상품을 먼저 보여 준다
        if intent in (None, "products", "order"):
            product = self._product_answer(text)
            if product:
                return product
        handler = getattr(self, f"_{intent}", None) if intent else None
        if handler:
            return handler(text, user)
        return self._free(text, user)

    @staticmethod
    def classify(text: str) -> str | None:
        t = text.lower().replace("?", "").strip()
        for intent, words in INTENTS:
            if any(w in t for w in words):
                return intent
        return None

    def sorry(self) -> dict:
        st = self.ctx.settings.load()
        msg = "잠시 문제가 생겼어요 🙏 조금 뒤 다시 보내 주세요."
        if st.factory_phone:
            msg += f"\n급하시면 {st.factory_phone} 로 전화 주세요."
        return respond(text_out(msg))

    # ---------------------------------------------------------------- 공용
    def _shop_url(self, path: str = "") -> str:
        return self.ctx.config.shop_link(path)

    def _phone_btn(self, st) -> list[dict]:
        return [{"label": "전화하기", "action": "phone", "phoneNumber": st.factory_phone}] if st.factory_phone else []

    def _shop_info(self):
        try:
            return self.ctx.services["web_order"].info()
        except AppError:
            return None  # 웹 주문서 꺼짐

    # ---------------------------------------------------------------- 규칙 답변
    def _menu_card(self, title: str = "무엇이 궁금하세요?") -> dict:
        st = self.ctx.settings.load()
        buttons = self._phone_btn(st)[:1] + [{"label": "주문서 열기", "action": "webLink", "webLinkUrl": self._shop_url()}]
        return menu_out(title, buttons)

    def _hello(self, text: str, user: str) -> dict:
        st = self.ctx.settings.load()
        hi = f"안녕하세요, {st.factory_name or '저희 공장'}이에요 😊"
        if st.shop_intro:
            hi += f"\n{st.shop_intro}"
        hi += "\n\n아래 메뉴에서 궁금한 걸 눌러 주세요."
        return respond(text_out(hi), self._menu_card(), menu=True)

    def _menu(self, text: str, user: str) -> dict:
        return respond(self._menu_card(), menu=True)

    def _products(self, text: str, user: str) -> dict:
        info = self._shop_info()
        if not info or not info.products:
            return self._phone(text, user)
        lines = []
        for p in info.products:
            price = f" {p.price:,}원" if p.price is not None else ""
            lines.append(f"· {p.name} {p.spec}{price}{' (품절)' if p.sold_out else ''}")
        body = "\n".join(lines)
        if not info.show_prices:
            body += "\n\n가격은 문의 주시면 안내드려요."
        return respond(
            text_out(f"🫙 지금 파는 젓갈이에요\n\n{body}"),
            card_out("주문은 여기서 해요", "상품을 골라 장바구니에 담고 주소만 적으면 끝!", [
                {"label": "주문서 열기", "action": "webLink", "webLinkUrl": self._shop_url()},
            ]),
        )

    def _product_answer(self, text: str) -> dict | None:
        """'명란 있어요?', '액젓 얼마예요' 처럼 상품 이름·별칭이 나오면 그 상품만 안내"""
        info = self._shop_info()
        if not info:
            return None
        shop = {p.sku: p for p in info.products}
        t = re.sub(r"\s", "", text)
        hits = []
        for p in self.ctx.products.list():
            if p.sku not in shop:
                continue
            names = {p.name, re.sub(r"\(.*?\)", "", p.name), *re.findall(r"\((.*?)\)", p.name)}
            names |= {a.strip() for a in p.aliases.replace("，", ",").split(",")}
            names |= {re.sub(r"(젓갈|젓)$", "", n) for n in list(names)}  # '명란젓' → '명란'
            if any(len(n) >= 2 and re.sub(r"\s", "", n) in t for n in names):
                hits.append(shop[p.sku])
        if not hits:
            return None
        lines = [
            f"· {p.name} {p.spec}" + (f" {p.price:,}원" if p.price is not None else "") + (" — 지금 품절이에요 😢" if p.sold_out else "")
            for p in hits
        ]
        desc = next((p.description for p in hits if p.description), "")
        msg = "\n".join(lines) + (f"\n\n{desc}" if desc else "")
        name = hits[0].name
        return respond(
            text_out(msg),
            card_out(name, "주문서에서 규격·수량을 골라 주문할 수 있어요.", [
                {"label": "이 상품 주문", "action": "webLink", "webLinkUrl": self._shop_url(f"/item/{_url(name)}")},
            ]),
        )

    def _order(self, text: str, user: str) -> dict:
        st = self.ctx.settings.load()
        info = self._shop_info()
        if not info:
            return respond(text_out(f"지금은 전화로 주문받고 있어요.\n☎ {st.factory_phone}"))
        return respond(
            card_out(
                "🛒 웹 주문서로 주문해요",
                "상품을 골라 받는 분·주소·받을 날만 적으면 끝이에요. 가입하면 다음부터 주소가 자동으로 채워져요."
                + (f"\n\n📢 {st.shop_notice}" if st.shop_notice else ""),
                [{"label": "주문서 열기", "action": "webLink", "webLinkUrl": self._shop_url()}] + self._phone_btn(st),
            )
        )

    def _shipping(self, text: str, user: str) -> dict:
        st = self.ctx.settings.load()
        if st.shop_shipping_fee:
            msg = f"🚚 택배비는 {st.shop_shipping_fee:,}원이에요."
            if st.shop_free_shipping_over:
                msg += f"\n{st.shop_free_shipping_over:,}원 이상 주문하시면 무료예요."
        elif st.shop_free_shipping_over:
            msg = f"🚚 {st.shop_free_shipping_over:,}원 이상 주문하시면 택배비가 무료예요. 그 아래는 주문 확인 후 안내드려요."
        else:
            msg = "🚚 택배비는 주문 확인 후 안내드려요."
        msg += f"\n양이 많으면({st.threshold_kg:g}kg 이상) 화물로 보내고, 운임은 따로 안내드려요."
        if st.shop_notice:
            msg += f"\n\n📢 {st.shop_notice}"
        return respond(text_out(msg))

    def _due(self, text: str, user: str) -> dict:
        st = self.ctx.settings.load()
        info = self._shop_info()
        closed = sorted(closed_weekdays(st.closed_days))
        msg = "📅 "
        leads = sorted({p.lead_days for p in info.products}) if info else []
        if info and len(leads) > 1:
            # 품목마다 준비 기간이 다르면 품목별로 알려 줘요
            msg += "주문 받고 바로 소분해서 보내 드려요. 준비 기간은 품목마다 달라요."
            for d in leads:
                names = ", ".join(f"{p.name} {p.spec}".strip() for p in info.products if p.lead_days == d)
                msg += f"\n · {names}: 주문 {d}일 뒤부터" if d else f"\n · {names}: 당일"
        elif info:
            msg += f"지금 주문하시면 {fmt_date_ko(info.min_due_date)}부터 받을 수 있어요."
        else:
            msg += f"주문 후 {st.self_order_lead_days}일 뒤부터 받을 수 있어요."
        if closed:
            msg += f"\n{', '.join(WEEKDAYS_KO[i] for i in closed)}요일은 택배가 쉬어서 받는 날로 고를 수 없어요."
        if st.shop_notice:
            msg += f"\n\n📢 {st.shop_notice}"
        return respond(text_out(msg))

    def _account(self, text: str, user: str) -> dict:
        st = self.ctx.settings.load()
        if not st.bank_account:
            return self._phone(text, user)
        return respond(text_out(
            f"💳 입금 계좌\n{st.bank_account}\n\n입금자명은 주문하신 분 성함으로 해 주세요. 금액은 주문 완료 화면이나 문자로 안내드려요."
        ))

    def _phone(self, text: str, user: str) -> dict:
        st = self.ctx.settings.load()
        if not st.factory_phone:
            return respond(text_out("전화번호가 아직 등록되지 않았어요. 주문서에서 주문해 주세요."))
        hours = f"\n문의 시간: {st.contact_hours}" if st.contact_hours else ""
        return respond(card_out(
            "☎ 전화 상담",
            f"{st.factory_name} {st.factory_phone}{hours}\n바쁠 때는 못 받을 수 있어요. 조금 뒤 다시 걸어 주세요.",
            self._phone_btn(st),
        ))

    # ---------------------------------------------------------------- 정해진 질문이 아닐 때
    def _free(self, text: str, user: str) -> dict:
        """글로 직접 물어본 경우 — 상담으로 넘기지 않고 메뉴만 다시 보여 준다"""
        st = self.ctx.settings.load()
        if text:
            self.ctx.logs.write("챗봇 질문", "카카오톡", text[:200], actor="챗봇")
        msg = "이 채팅은 글로 답해 드리지 않아요 🙏\n아래 메뉴에서 골라 주세요."
        if st.factory_phone:
            msg += f"\n그 밖의 문의는 {st.factory_phone} 로 전화 주세요."
        return respond(text_out(msg), self._menu_card("메뉴"), menu=True)


def _url(s: str) -> str:
    from urllib.parse import quote

    return quote(s, safe="")
