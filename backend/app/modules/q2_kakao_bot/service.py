"""카카오톡 챗봇 답변 만들기.

카카오 스킬은 5초 안에 답해야 해서:
1) 규칙으로 바로 답할 수 있는 질문(상품·가격, 택배비, 받는 날, 계좌, 주문 조회, 전화, 주문하기)은 규칙으로
2) 나머지는 AI(있으면)가 3.5초 안에, 공장 정보만 보고 짧게
3) 그래도 못 하면 "전화 주세요" + 빠른 메뉴
답을 못 한 질문은 _기록 탭에 '챗봇 질문'으로 남겨서 부모님이 자주 묻는 걸 볼 수 있게 한다.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from ...core.errors import AppError
from ...core.timeutil import fmt_date_ko, today
from ...integrations.claude_client import ClaudeUnavailable
from ...schemas.settings import WEEKDAYS_KO, closed_weekdays

log = logging.getLogger(__name__)

ORDER_ID_RE = re.compile(r"[Oo]-?\s?(\d{8})-?\s?(\d{3})")
QUICK = ["상품·가격", "주문하기", "택배비", "받는 날", "주문 조회", "입금 계좌", "전화 연결"]

# 질문 종류 → 알아듣는 말 (앞에 있을수록 먼저)
INTENTS: list[tuple[str, tuple[str, ...]]] = [
    ("lookup", ("주문 조회", "주문조회", "조회", "송장", "배송 조회", "어디쯤", "언제 와", "언제와", "도착", "출발했", "보냈", "내 주문")),
    ("order", ("주문하기", "주문할", "주문 할", "주문하고", "사고 싶", "살게", "구매", "구입", "보내 주세요", "보내주세요", "주문서")),
    ("account", ("계좌", "입금", "송금", "이체", "통장")),
    ("shipping", ("택배비", "배송비", "배달비", "무료배송", "무료 배송", "택배")),
    ("due", ("받는 날", "언제 받", "며칠", "도착일", "배송일", "출고", "휴무", "쉬는 날", "주말")),
    ("phone", ("전화", "통화", "상담", "사장님", "사람")),
    ("products", ("상품", "가격", "얼마", "메뉴", "종류", "뭐 팔", "뭐팔", "품목", "판매")),
    ("hello", ("안녕", "처음", "시작", "도움", "help", "hi", "hello")),
]


def _quick(labels: list[str] | None = None) -> list[dict]:
    return [{"label": l, "action": "message", "messageText": l} for l in (labels or QUICK)][:10]


def text_out(text: str) -> dict:
    return {"simpleText": {"text": text[:1000]}}


def card_out(title: str, desc: str, buttons: list[dict]) -> dict:
    return {"textCard": {"title": title[:50], "description": desc[:400], "buttons": buttons[:3]}}


def respond(*outputs: dict, quick: list[str] | None = None) -> dict:
    return {"version": "2.0", "template": {"outputs": list(outputs)[:3] or [text_out("…")], "quickReplies": _quick(quick)}}


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
        if intent in (None, "products", "hello", "order"):
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
        if ORDER_ID_RE.search(text):
            return "lookup"
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
        return f"{self.ctx.config.public_web_url.rstrip('/')}/shop{path}"

    def _phone_btn(self, st) -> list[dict]:
        return [{"label": "전화하기", "action": "phone", "phoneNumber": st.factory_phone}] if st.factory_phone else []

    def _shop_info(self):
        try:
            return self.ctx.services["web_order"].info()
        except AppError:
            return None  # 웹 주문서 꺼짐

    # ---------------------------------------------------------------- 규칙 답변
    def _hello(self, text: str, user: str) -> dict:
        st = self.ctx.settings.load()
        hi = f"안녕하세요, {st.factory_name or '저희 공장'}이에요 😊"
        if st.shop_intro:
            hi += f"\n{st.shop_intro}"
        hi += "\n\n궁금한 걸 편하게 물어보세요. 아래 버튼을 눌러도 돼요."
        return respond(text_out(hi))

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
        if info:
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
            return respond(text_out("이 채팅으로 남겨 주시면 확인하고 연락드릴게요."))
        return respond(card_out("☎ 전화 상담", f"{st.factory_name} {st.factory_phone}\n바쁠 때는 못 받을 수 있어요. 문자 남겨 주시면 연락드려요.", self._phone_btn(st)))

    def _lookup(self, text: str, user: str) -> dict:
        m = ORDER_ID_RE.search(text)
        tail = re.findall(r"(?<!\d)(\d{4})(?!\d)", ORDER_ID_RE.sub(" ", text))
        if not m or not tail:
            return respond(
                text_out("📦 주문번호와 휴대폰 번호 뒤 4자리를 같이 보내 주세요.\n예) O-20261126-003 5678\n\n가입하셨으면 주문서 마이페이지에서 모든 주문을 볼 수 있어요."),
                card_out("마이페이지", "로그인하면 주문 내역·입금·송장을 한 번에 봐요.", [
                    {"label": "마이페이지", "action": "webLink", "webLinkUrl": self._shop_url("/my")},
                ]),
            )
        oid = f"O-{m.group(1)}-{m.group(2)}"
        key = "kakao:" + hashlib.sha256(user.encode()).hexdigest()[:16] if user else "kakao"
        try:
            o = self.ctx.services["web_order"].lookup(oid, tail[-1], key)
        except AppError as e:
            return respond(text_out(f"😥 {e.message}"))
        status = {"접수": "주문 확인·준비 중이에요", "출고대기": "포장 끝, 곧 보내요", "출고완료": "보냈어요 🚚", "취소": "취소된 주문이에요"}.get(o.status, o.status)
        msg = f"📦 {o.order_id}\n{status}\n\n품목: {o.items}\n받는 날: {o.due_date}\n입금: {'확인됐어요 ✔' if o.paid else '확인 전이에요'}"
        outs = [text_out(msg)]
        if o.tracking_no:
            outs.append(card_out(f"{o.carrier} {o.tracking_no}", "배송 위치를 확인해 보세요.", [
                {"label": "배송 조회", "action": "webLink",
                 "webLinkUrl": f"https://search.naver.com/search.naver?query={_url(o.carrier + ' ' + o.tracking_no)}"},
            ]))
        return respond(*outs)

    # ---------------------------------------------------------------- 자유 질문
    def _facts(self) -> str:
        st = self.ctx.settings.load()
        info = self._shop_info()
        lines = [f"공장: {st.factory_name} / 전화 {st.factory_phone} / 주소 {st.factory_address}"]
        if st.shop_intro:
            lines.append(f"소개: {st.shop_intro}")
        if st.shop_notice:
            lines.append(f"공지: {st.shop_notice}")
        if info:
            for p in info.products:
                lines.append(
                    f"상품: {p.name} {p.spec} ({p.unit})"
                    + (f" {p.price:,}원" if p.price is not None else "")
                    + (" 품절" if p.sold_out else "")
                    + (f" — {p.description}" if p.description else "")
                )
            lines.append(f"가장 빠른 받는 날: {fmt_date_ko(info.min_due_date)}, 쉬는 요일: {info.closed_days_text or '없음'}")
        lines.append(
            f"택배비: {st.shop_shipping_fee:,}원" if st.shop_shipping_fee else "택배비: 주문 확인 후 안내"
        )
        if st.shop_free_shipping_over:
            lines.append(f"{st.shop_free_shipping_over:,}원 이상 무료배송")
        if st.bank_account:
            lines.append(f"입금 계좌: {st.bank_account}")
        lines.append(f"주문서 주소: {self._shop_url()}")
        lines.append(f"오늘: {fmt_date_ko(today())}")
        return "\n".join(lines)

    def _free(self, text: str, user: str) -> dict:
        st = self.ctx.settings.load()
        claude = self.ctx.claude
        if text and claude.enabled:
            system = (
                "너는 작은 젓갈 공장의 카카오톡 채널 상담원이다. 손님에게 존댓말로, 3~4문장 안으로 짧고 따뜻하게 답한다.\n"
                "아래 [공장 정보]에 있는 사실만 말한다. 없는 건 지어내지 말고 '전화로 문의해 주세요'라고 안내한다.\n"
                "가격·재고·배송 날짜를 약속하지 않는다. 주문은 주문서 주소로 안내한다. 이모지는 1개까지.\n"
                "건강·의학적 효능은 말하지 않는다. 젓갈과 상관없는 요청은 정중히 사양한다.\n\n"
                f"[공장 정보]\n{self._facts()}"
            )
            try:
                reply = claude.complete(system=system, user=text[:500], max_tokens=300, timeout=3.5)
                return respond(text_out(reply))
            except ClaudeUnavailable as e:
                log.info("kakao bot AI skipped: %s", e)
        self.ctx.logs.write("챗봇 질문", "카카오톡", text[:200], actor="챗봇")
        msg = "질문을 잘 못 알아들었어요 🙏 아래 버튼에서 골라 주시거나,"
        msg += f"\n{st.factory_phone} 로 전화 주세요." if st.factory_phone else " 남겨 주시면 확인하고 연락드릴게요."
        return respond(text_out(msg))


def _url(s: str) -> str:
    from urllib.parse import quote

    return quote(s, safe="")
