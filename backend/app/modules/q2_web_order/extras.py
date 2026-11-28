"""웹 주문서 부가 기능 — 손님 직접 취소 · 구매 후기 · 카카오 로그인.

WebOrderService 가 이 클래스를 함께 물려받는다 (self.ctx, self.member, self._key … 를 같이 씀).

손님 직접 취소
  - '주문 접수' 상태(포장 전)만. 계좌 입금이 이미 확인된 주문은 돈을 돌려드려야 해서 전화로.
  - 카드·간편결제 주문은 취소하면 자동 환불 (주문 서비스의 refund_hook).

구매 후기
  - 출고가 끝난 주문의 품목만, 주문·품목마다 1개. 별점 1~5 + 한 줄(300자).
  - 작성자 이름은 가운데를 가린다(최*제). 부모님이 '후기' 탭 '숨김'을 예로 하면 안 보임.

카카오 로그인
  - [카카오로 시작하기] → 카카오 동의 → 우리 서버 callback → 카카오 회원번호로 손님 찾기
  - 처음이면 이름·휴대폰만 한 번 적으면 가입 (같은 번호로 비밀번호 가입한 계정이 있으면 비밀번호로 연결)
  - 카카오 계정만 있는 손님은 '웹로그인' 칸에 'kakao:임의값'이 들어가 토큰 검증에 쓰인다 (비밀번호 로그인은 안 됨)
"""

from __future__ import annotations

import base64
import secrets
from typing import Any
from urllib.parse import urlencode

from pydantic import BaseModel, Field, field_validator

from ...core.errors import NotFoundError, UnauthorizedError, ValidationFailed
from ...core.repository import Repository
from ...core.sheet_schema import REVIEWS
from ...core.signing import sign, verify
from ...core.timeutil import now
from ...schemas.customer import CustomerOut
from ..q2_self_order.service import PublicOrderOut, to_public
from .accounts import check_password, issue_token

KAUTH = "https://kauth.kakao.com"
KAPI = "https://kapi.kakao.com"


def mask_name(name: str) -> str:
    n = (name or "").strip()
    if len(n) <= 1:
        return n or "손님"
    if len(n) == 2:
        return n[0] + "*"
    return n[0] + "*" * (len(n) - 2) + n[-1]


# ---------------------------------------------------------------- 후기 모델
class ReviewIn(BaseModel):
    order_id: str = Field(min_length=6, max_length=64)
    sku: str = Field(min_length=1, max_length=40)
    rating: int = Field(ge=1, le=5)
    text: str = Field(default="", max_length=300)
    phone4: str = Field(default="", max_length=4, description="비회원은 주문 조회처럼 전화 뒤 4자리")

    @field_validator("text", mode="before")
    @classmethod
    def _strip(cls, v):
        return " ".join((v or "").split())


class ReviewOut(BaseModel):
    review_id: str
    created_at: str
    product_name: str
    spec: str
    author: str
    rating: int
    text: str


class ReviewAdminOut(ReviewOut):
    order_id: str
    customer_id: str
    hidden: bool


class ReviewList(BaseModel):
    average: float | None
    count: int
    items: list[ReviewOut]


class CancelIn(BaseModel):
    order_id: str = Field(min_length=6, max_length=64)
    phone4: str = Field(default="", max_length=4)


class KakaoCompleteIn(BaseModel):
    ticket: str = Field(min_length=10, max_length=600)
    name: str = Field(min_length=1, max_length=30)
    phone: str = Field(min_length=9, max_length=20)
    company: str = Field(default="", max_length=40)
    password: str = Field(default="", max_length=40, description="같은 번호로 이미 가입했으면 그 비밀번호 (연결)")
    agree_privacy: bool

    @field_validator("name", "company", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip()


class KakaoResult(BaseModel):
    """callback 이 웹 화면으로 넘기는 값: 바로 로그인(token) 또는 처음이라 이름·번호 입력(ticket)"""
    token: str = ""
    ticket: str = ""
    nickname: str = ""


class ShopExtrasMixin:
    ctx: Any

    # 아래는 WebOrderService 에 있는 것들 (lookup_limiter, _secret, member, _rows_by_phone …)
    lookup_limiter: Any

    @property
    def _key(self) -> str:
        return str(getattr(self, "_secret"))

    # ================================================================ 손님 직접 취소
    def _my_order(self, order_id: str, *, token: str = "", phone4: str = ""):
        from .service import digits

        oid = (order_id or "").strip().upper()
        try:
            o = self.ctx.orders.get(oid, fresh=True)
        except NotFoundError:
            o = None
        if o is not None and token:
            if o.customer_id == self.member(token).customer_id:  # type: ignore[attr-defined]
                return o
        elif o is not None and len(digits(phone4)) == 4 and digits(o.phone).endswith(digits(phone4)):
            return o
        raise NotFoundError("주문을 찾지 못했어요.")

    @staticmethod
    def cancel_block_reason(o) -> str:
        """손님이 직접 취소할 수 없으면 그 이유 (취소 가능하면 '')"""
        if o.status == "취소":
            return "이미 취소된 주문이에요."
        if o.status != "접수":
            return "포장을 시작해서 직접 취소할 수 없어요. 공장에 전화해 주세요."
        if o.paid_at is not None and not o.pay_key:
            return "입금이 확인된 주문이라 환불을 위해 공장에 전화해 주세요."
        return ""

    def cancel_by_customer(self, body: CancelIn, token: str = "", client_ip: str = "") -> PublicOrderOut:
        if not token:
            key = client_ip or "anon"
            self.lookup_limiter.check(key)
            self.lookup_limiter.hit(key)
        o = self._my_order(body.order_id, token=token, phone4=body.phone4)
        why = self.cancel_block_reason(o)
        if why:
            raise ValidationFailed(why)
        out = self.ctx.orders.cancel(o.order_id, actor=f"손님:{o.recipient or o.customer_name}")
        self.ctx.logs.write("손님 주문 취소", o.order_id, o.customer_name, actor="웹주문서")
        try:  # 부모님께도 알림 (켜져 있으면)
            if getattr(self.ctx, "kakao", None) and self.ctx.kakao.configured:
                web = (self.ctx.config.public_web_url or "").rstrip("/")
                self.ctx.kakao.send_text(
                    f"🙅 손님이 주문을 취소했어요\n{o.order_id} · {o.customer_name}\n"
                    + ", ".join(f"{l.product_name} {l.qty}" for l in o.lines),
                    link_url=f"{web}/orders",
                )
        except Exception:  # 알림 실패는 취소에 영향 없음
            pass
        return to_public(out)

    # ================================================================ 구매 후기
    @property
    def _reviews(self) -> Repository[dict]:
        repo = getattr(self, "_review_repo", None)
        if repo is None:
            repo = Repository(self.ctx.sheets, REVIEWS)
            self._review_repo = repo
        return repo

    def _review_rows(self, fresh: bool = False) -> list[dict]:
        return [r.data for r in self._reviews.all(fresh) if r.data.get("review_id")]

    def reviewed_keys(self, customer_id: str = "", order_id: str = "") -> set[tuple[str, str]]:
        return {
            (str(d.get("order_id")), str(d.get("sku")))
            for d in self._review_rows(fresh=True)
            if (not customer_id or d.get("customer_id") == customer_id) and (not order_id or d.get("order_id") == order_id)
        }

    def _spec_of(self, sku: str) -> tuple[str, str]:
        p = self.ctx.products.map().get(sku)
        return (p.name, p.spec) if p else ("", "")

    def _review_out(self, d: dict) -> ReviewOut:
        name, spec = self._spec_of(str(d.get("sku") or ""))
        ts = d.get("created_at")
        return ReviewOut(
            review_id=str(d.get("review_id")), created_at=ts.strftime("%Y.%m.%d") if ts else "",
            product_name=str(d.get("product_name") or name), spec=spec, author=str(d.get("author") or "손님"),
            rating=int(d.get("rating") or 0), text=str(d.get("text") or ""),
        )

    def review_summary(self) -> dict[str, tuple[float, int]]:
        """상품 이름 → (평균 별점, 개수) — 숨긴 후기는 빼고"""
        acc: dict[str, list[int]] = {}
        for d in self._review_rows():
            if d.get("hidden") or not d.get("rating"):
                continue
            acc.setdefault(str(d.get("product_name") or ""), []).append(int(d["rating"]))
        return {k: (round(sum(v) / len(v), 1), len(v)) for k, v in acc.items() if v}

    def list_reviews(self, product_name: str, limit: int = 30) -> ReviewList:
        rows = [d for d in self._review_rows() if not d.get("hidden") and d.get("product_name") == product_name]
        rows.sort(key=lambda d: str(d.get("created_at") or ""), reverse=True)
        ratings = [int(d.get("rating") or 0) for d in rows if d.get("rating")]
        return ReviewList(
            average=round(sum(ratings) / len(ratings), 1) if ratings else None,
            count=len(rows), items=[self._review_out(d) for d in rows[:limit]],
        )

    def write_review(self, body: ReviewIn, token: str = "", client_ip: str = "") -> ReviewOut:
        if not token:
            key = client_ip or "anon"
            self.lookup_limiter.check(key)
            self.lookup_limiter.hit(key)
        o = self._my_order(body.order_id, token=token, phone4=body.phone4)
        if o.status != "출고완료":
            raise ValidationFailed("물건을 받으신 뒤(출고 완료 후)에 후기를 쓸 수 있어요.")
        line = next((l for l in o.lines if l.sku == body.sku), None)
        if line is None:
            raise ValidationFailed("이 주문에 없는 상품이에요.")
        if (o.order_id, body.sku) in self.reviewed_keys(order_id=o.order_id):
            raise ValidationFailed("이 상품 후기는 이미 쓰셨어요.")
        name, _ = self._spec_of(body.sku)
        existing = [str(d.get("review_id")) for d in self._review_rows(fresh=True)]
        rid = f"R{len(existing) + 1:05d}"
        while rid in existing:
            rid = f"R{secrets.randbelow(10**6):06d}"
        row = {
            "review_id": rid, "created_at": now(), "product_name": name or line.product_name, "sku": body.sku,
            "order_id": o.order_id, "customer_id": o.customer_id, "author": mask_name(o.recipient or o.customer_name),
            "rating": body.rating, "text": body.text, "hidden": False,
        }
        self._reviews.insert(row)
        self.ctx.logs.write("후기 작성", o.order_id, f"{name} ★{body.rating}", actor="웹주문서")
        return self._review_out(row)

    # 관리자
    def admin_reviews(self) -> list[ReviewAdminOut]:
        rows = self._review_rows(fresh=True)
        rows.sort(key=lambda d: str(d.get("created_at") or ""), reverse=True)
        return [
            ReviewAdminOut(**self._review_out(d).model_dump(), order_id=str(d.get("order_id") or ""),
                           customer_id=str(d.get("customer_id") or ""), hidden=bool(d.get("hidden")))
            for d in rows
        ]

    def hide_review(self, review_id: str, hidden: bool) -> ReviewAdminOut:
        cur = self._reviews.get(review_id, fresh=True)
        if cur is None:
            raise NotFoundError("후기를 찾지 못했어요.")
        self._reviews.update((review_id,), {"hidden": hidden})
        self.ctx.logs.write("후기 숨김" if hidden else "후기 보이기", review_id, "", actor="관리자")
        d = {**cur, "hidden": hidden}
        return ReviewAdminOut(**self._review_out(d).model_dump(), order_id=str(d.get("order_id") or ""),
                              customer_id=str(d.get("customer_id") or ""), hidden=hidden)

    # ================================================================ 카카오 로그인
    @property
    def kakao_login_enabled(self) -> bool:
        return bool(self.ctx.config.kakao_rest_api_key)

    @property
    def kakao_redirect(self) -> str:
        return f"{self.ctx.config.public_api_url.rstrip('/')}/api/public/shop/auth/kakao/callback"

    def kakao_start_url(self) -> str:
        if not self.kakao_login_enabled:
            raise ValidationFailed("카카오 로그인이 아직 꺼져 있어요.")
        state = sign(self._key, f"klogin:{secrets.token_hex(8)}", 600)
        q = {"client_id": self.ctx.config.kakao_rest_api_key, "redirect_uri": self.kakao_redirect,
             "response_type": "code", "state": state}
        return f"{KAUTH}/oauth/authorize?{urlencode(q)}"

    def _kakao_user(self, code: str) -> tuple[str, str]:
        from .service import _http_of

        http = _http_of(self.ctx)
        cfg = self.ctx.config
        form = {"grant_type": "authorization_code", "client_id": cfg.kakao_rest_api_key,
                "redirect_uri": self.kakao_redirect, "code": code}
        if cfg.kakao_client_secret:
            form["client_secret"] = cfg.kakao_client_secret
        r = http("POST", f"{KAUTH}/oauth/token", form=form, timeout=10)
        data = r.json() if r.body else {}
        if not r.ok or not isinstance(data, dict) or not data.get("access_token"):
            raise ValidationFailed("카카오 로그인에 실패했어요. 다시 시도해 주세요.")
        me = http("GET", f"{KAPI}/v2/user/me", headers={"Authorization": f"Bearer {data['access_token']}"}, timeout=10)
        info = me.json() if me.body else {}
        if not me.ok or not isinstance(info, dict) or not info.get("id"):
            raise ValidationFailed("카카오 회원 정보를 받지 못했어요.")
        props = info.get("properties") if isinstance(info.get("properties"), dict) else {}
        nick = str((props or {}).get("nickname") or "")
        return str(info["id"]), nick

    def _row_by_kakao(self, kid: str) -> dict | None:
        for d in self.ctx.customers.rows(fresh=True):
            if d.get("customer_id") and str(d.get("kakao_id") or "") == kid and d.get("active") is not False:
                return d
        return None

    def kakao_callback(self, code: str, state: str) -> KakaoResult:
        if not (verify(self._key, state or "") or "").startswith("klogin:"):
            raise UnauthorizedError("로그인 시간이 지났어요. 다시 시도해 주세요.")
        kid, nick = self._kakao_user(code)
        row = self._row_by_kakao(kid)
        if row is not None and row.get("web_password"):
            return KakaoResult(token=issue_token(self._key, row["customer_id"], row["web_password"]), nickname=nick)
        nick_b64 = base64.urlsafe_b64encode(nick.encode()).decode()[:80]
        return KakaoResult(ticket=sign(self._key, f"kakao:{kid}:{nick_b64}", 1800), nickname=nick)

    def kakao_complete(self, body: KakaoCompleteIn) -> Any:
        """처음 카카오로 온 손님: 이름·번호로 가입하거나 기존 계정에 연결"""
        from .service import MOBILE_RE, AuthOut, GuestOrderIn, _attachable, _profile, digits, pretty_phone

        payload = verify(self._key, body.ticket) or ""
        if not payload.startswith("kakao:"):
            raise UnauthorizedError("시간이 지났어요. 카카오로 다시 시작해 주세요.")
        kid = payload.split(":")[1]
        if not body.agree_privacy:
            raise ValidationFailed("개인정보 수집·이용에 동의해 주셔야 가입할 수 있어요.")
        if not MOBILE_RE.match(digits(body.phone)):
            raise ValidationFailed("휴대폰 번호를 확인해 주세요 (예: 010-1234-5678).")
        if self._row_by_kakao(kid):
            raise ValidationFailed("이미 연결된 카카오 계정이에요. 카카오로 다시 로그인해 주세요.")
        phone = pretty_phone(body.phone)
        rows = self._rows_by_phone(phone)  # type: ignore[attr-defined]
        with_pw = [r for r in rows if r.get("web_password")]
        if with_pw:
            # 같은 번호로 가입한 계정 → 그 비밀번호를 알아야 연결 (남의 계정 가로채기 방지)
            hit = next((r for r in with_pw if check_password(body.password, r.get("web_password") or "")), None)
            if hit is None:
                raise ValidationFailed("이 번호로 가입한 계정이 있어요. 그 계정 비밀번호를 넣으면 카카오와 연결돼요.")
            self.ctx.customers.update((hit["customer_id"],), {"kakao_id": kid})
            self.ctx.logs.write("카카오 연결", hit["customer_id"], hit.get("name", ""), actor="웹주문서")
            c = CustomerOut.from_row(self.ctx.customers.get(hit["customer_id"], fresh=True) or {})
            return AuthOut(token=issue_token(self._key, c.customer_id, hit["web_password"]), profile=_profile(c))
        probe = GuestOrderIn.model_construct(name=body.name, company=body.company, phone=phone, address="", zipcode="")
        same = [CustomerOut.from_row(r) for r in rows]
        found = next((x for x in same if _attachable(x) and self._same_person(x, probe)), None)  # type: ignore[attr-defined]
        c = found or self._new_customer(probe, phone, same)  # type: ignore[attr-defined]
        marker = f"kakao:{secrets.token_hex(12)}"
        self.ctx.customers.update((c.customer_id,), {"kakao_id": kid, "web_password": marker, "privacy_agreed_at": now()})
        self.ctx.logs.write("카카오 가입", c.customer_id, c.name, actor="웹주문서")
        fresh = CustomerOut.from_row(self.ctx.customers.get(c.customer_id, fresh=True) or {})
        return AuthOut(token=issue_token(self._key, c.customer_id, marker), profile=_profile(fresh))
