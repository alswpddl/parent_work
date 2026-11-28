"""웹 주문서 부가 기능: 손님 직접 취소 · 구매 후기 · 영수증 요청 · 카카오 로그인"""
import pytest

from app.core.errors import NotFoundError, UnauthorizedError, ValidationFailed
from app.modules.q2_web_order.extras import CancelIn, KakaoCompleteIn, ReviewIn, mask_name
from app.modules.q2_web_order.service import SignupIn
from tests.test_web_order import _body, _svc


def test_customer_cancel_rules(full_ctx):
    s = _svc(full_ctx)
    done = s.place(_body())
    tail = "8888"
    # 남의 번호로는 못 함
    with pytest.raises(NotFoundError):
        s.cancel_by_customer(CancelIn(order_id=done.order_id, phone4="0000"))
    out = s.cancel_by_customer(CancelIn(order_id=done.order_id, phone4=tail))
    assert out.status == "취소"
    with pytest.raises(ValidationFailed, match="이미 취소"):
        s.cancel_by_customer(CancelIn(order_id=done.order_id, phone4=tail))

    # 계좌 입금 확인된 주문 → 전화로
    d2 = s.place(_body(client_token="t2"))
    full_ctx.orders.set_paid(d2.order_id, True)
    with pytest.raises(ValidationFailed, match="전화"):
        s.cancel_by_customer(CancelIn(order_id=d2.order_id, phone4=tail))
    # 포장 시작(출고대기) → 전화로
    d3 = s.place(_body(client_token="t3"))
    full_ctx.orders.ship(d3.order_id)
    with pytest.raises(ValidationFailed, match="포장"):
        s.cancel_by_customer(CancelIn(order_id=d3.order_id, phone4=tail))


def test_reviews_only_after_shipping(full_ctx):
    s = _svc(full_ctx)
    done = s.place(_body())
    o = full_ctx.orders.get(done.order_id)
    sku = o.lines[0].sku
    with pytest.raises(ValidationFailed, match="받으신 뒤"):
        s.write_review(ReviewIn(order_id=o.order_id, sku=sku, rating=5, text="맛있어요", phone4="8888"))
    full_ctx.orders.ship(o.order_id)
    r = s.write_review(ReviewIn(order_id=o.order_id, sku=sku, rating=4, text="  깔끔하고   좋아요 ", phone4="8888"))
    assert r.rating == 4 and r.text == "깔끔하고 좋아요" and "*" in r.author
    with pytest.raises(ValidationFailed, match="이미"):
        s.write_review(ReviewIn(order_id=o.order_id, sku=sku, rating=5, phone4="8888"))
    with pytest.raises(ValidationFailed, match="없는 상품"):
        s.write_review(ReviewIn(order_id=o.order_id, sku="NOPE", rating=5, phone4="8888"))
    name = r.product_name
    lst = s.list_reviews(name)
    assert lst.count == 1 and lst.average == 4.0
    p = next(p for p in s.info().products if p.sku == sku)
    assert p.review_count == 1 and p.review_avg == 4.0
    # 부모님이 숨기면 안 보임
    s.hide_review(r.review_id, True)
    assert s.list_reviews(name).count == 0
    assert mask_name("최민제") == "최*제" and mask_name("김철") == "김*"


def test_receipt_request_goes_to_note(full_ctx):
    s = _svc(full_ctx)
    with pytest.raises(ValidationFailed, match="사업자등록번호"):
        s.place(_body(receipt_type="세금계산서", receipt_id="123", receipt_email="a@b.kr"))
    done = s.place(_body(receipt_type="세금계산서", receipt_id="123-45-67890", receipt_email="a@b.kr", note="문 앞"))
    note = full_ctx.orders.get(done.order_id).note
    assert note.startswith("[세금계산서 123-45-67890 a@b.kr]") and "문 앞" in note
    d2 = s.place(_body(receipt_type="현금영수증", receipt_id="010-1234-5678", client_token="r2"))
    assert full_ctx.orders.get(d2.order_id).note.startswith("[현금영수증 010-1234-5678]")


def test_my_orders_flags(full_ctx):
    s = _svc(full_ctx)
    auth = s.signup(SignupIn(name="최민제", phone="010-5555-1234", password="abcd1234", address="통영시", agree_privacy=True))
    done = s.place(_body(name="최민제", phone="010-5555-1234"), token=auth.token)
    mine = s.my_orders(auth.token)[0]
    assert mine.can_cancel and mine.reviewable == []
    full_ctx.orders.ship(done.order_id)
    mine = s.my_orders(auth.token)[0]
    assert not mine.can_cancel and mine.reviewable


def test_kakao_login_new_and_link(full_ctx, http):
    s = _svc(full_ctx)
    url = s.kakao_start_url()
    assert "kauth.kakao.com/oauth/authorize" in url and "redirect_uri=" in url
    state = url.split("state=")[1]
    with pytest.raises(UnauthorizedError):
        s.kakao_callback("code", "엉터리")

    # 처음 온 카카오 손님 → ticket → 이름·번호로 가입
    http.queue("/v2/user/me", 200, {"id": 111, "properties": {"nickname": "민제"}})
    r = s.kakao_callback("code1", state)
    assert r.ticket and not r.token and r.nickname == "민제"
    auth = s.kakao_complete(KakaoCompleteIn(ticket=r.ticket, name="최민제", phone="010-7777-1111", agree_privacy=True))
    assert s.member(auth.token).name
    # 다음부터는 바로 로그인
    http.queue("/v2/user/me", 200, {"id": 111})
    assert s.kakao_callback("code2", state).token
    # 카카오 손님은 비밀번호 없이 새 비밀번호를 만들 수 있음
    from app.modules.q2_web_order.service import PasswordIn

    s.change_password(auth.token, PasswordIn(new_password="newpw12"))

    # 같은 번호로 비밀번호 가입한 계정 → 비밀번호를 알아야 연결
    s.signup(SignupIn(name="박영희", phone="010-8888-2222", password="pw1234", agree_privacy=True))
    http.queue("/v2/user/me", 200, {"id": 222})
    t = s.kakao_callback("code3", state).ticket
    with pytest.raises(ValidationFailed, match="비밀번호"):
        s.kakao_complete(KakaoCompleteIn(ticket=t, name="박영희", phone="010-8888-2222", password="틀림", agree_privacy=True))
    linked = s.kakao_complete(KakaoCompleteIn(ticket=t, name="박영희", phone="010-8888-2222", password="pw1234", agree_privacy=True))
    assert linked.token
    http.queue("/v2/user/me", 200, {"id": 222})
    assert s.kakao_callback("code4", state).token


def test_google_login_new_then_direct(full_ctx, http):
    s = _svc(full_ctx)
    with pytest.raises(ValidationFailed, match="구글"):
        s.google_start_url()  # 키 없으면 꺼짐
    full_ctx.config.google_client_id = "gid.apps.googleusercontent.com"
    full_ctx.config.google_client_secret = "gsecret"
    url = s.google_start_url()
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?") and "scope=openid+email+profile" in url
    assert "api.example.com%2Fapi%2Fpublic%2Fshop%2Fauth%2Fgoogle%2Fcallback" in url
    state = url.split("state=")[1].split("&")[0]
    with pytest.raises(UnauthorizedError):
        s.google_callback("c", s.kakao_start_url().split("state=")[1])  # 카카오 표로는 안 됨

    http.queue("oauth2.googleapis.com/token", 200, {"access_token": "g-acc", "id_token": "x"})
    http.queue("openidconnect.googleapis.com", 200, {"sub": "g-123", "name": "Minje Choi", "email": "m@example.com"})
    r = s.google_callback("code1", state)
    assert r.ticket and not r.token and r.nickname == "Minje Choi"
    tok = http.by("oauth2.googleapis.com/token")[0]["form"]
    assert tok["client_secret"] == "gsecret" and tok["code"] == "code1"

    auth = s.kakao_complete(KakaoCompleteIn(ticket=r.ticket, name="최민제", phone="010-7777-3333", agree_privacy=True))
    row = full_ctx.customers.get(s.member(auth.token).customer_id, fresh=True)
    assert row["google_id"] == "g-123" and not row.get("kakao_id")

    http.queue("oauth2.googleapis.com/token", 200, {"access_token": "g-acc2"})
    http.queue("openidconnect.googleapis.com", 200, {"sub": "g-123"})
    assert s.google_callback("code2", state).token  # 다음부터는 바로 로그인

    http.queue("oauth2.googleapis.com/token", 400, {"error": "invalid_grant"})
    with pytest.raises(ValidationFailed, match="구글 로그인에 실패"):
        s.google_callback("bad", state)


def test_password_signup_closed_by_default(full_ctx):
    s = _svc(full_ctx)
    full_ctx.config.allow_password_signup = False
    with pytest.raises(ValidationFailed, match="카카오나 구글"):
        s.signup(SignupIn(name="아무개", phone="010-1111-2222", password="1234", agree_privacy=True))
    # 주문하면서 비밀번호를 보내도 가입은 안 되고 주문만 들어감
    done = s.place(_body(password="1234", client_token="pw-off"))
    assert done.order_id and not done.token


def test_guest_lookup_with_sms_code(full_ctx, http):
    import re as _re

    from app.modules.q2_web_order.extras import GuestCodeIn, GuestVerifyIn

    s = _svc(full_ctx)
    assert s.sms_verify_enabled  # 테스트 설정엔 솔라피 키·발신번호가 있음
    mine = s.place(_body(client_token="g1"))  # 010-7777-8888 로 주문
    out = s.guest_send_code(GuestCodeIn(name="김 영희", phone="010-7777-8888"), "1.2.3.4")
    sms = http.by("api.solapi.com")[-1]["json"]["messages"][0]
    assert sms["to"] == "01077778888" and sms["from"] == "0310000000" and "인증번호" in sms["text"]
    code = _re.search(r"\[(\d{6})\]", sms["text"]).group(1)

    with pytest.raises(ValidationFailed, match="맞지 않아요"):
        s.guest_orders(GuestVerifyIn(name="김영희", phone="01077778888", code="000000" if code != "000000" else "111111", verify_token=out.verify_token))
    with pytest.raises(UnauthorizedError):  # 다른 번호로 표 재사용 불가
        s.guest_orders(GuestVerifyIn(name="김영희", phone="010-1234-5678", code=code, verify_token=out.verify_token))
    found = s.guest_orders(GuestVerifyIn(name="김영희", phone="010-7777-8888", code=code, verify_token=out.verify_token))
    assert [o.order_id for o in found] == [mine.order_id]
    # 이름이 다르면 같은 번호여도 안 보임
    assert s.guest_orders(GuestVerifyIn(name="박철수", phone="010-7777-8888", code=code, verify_token=out.verify_token)) == []


def test_guest_code_limits_and_off(full_ctx):
    from app.core.errors import TooManyRequests
    from app.modules.q2_web_order.extras import GuestCodeIn

    s = _svc(full_ctx)
    for _ in range(5):
        s.guest_send_code(GuestCodeIn(name="김영희", phone="010-7777-9999"), "9.9.9.9")
    with pytest.raises(TooManyRequests):
        s.guest_send_code(GuestCodeIn(name="김영희", phone="010-7777-9999"), "9.9.9.9")
    full_ctx.solapi.sender = ""  # 발신번호 없으면 꺼짐 → 주문번호 조회로
    assert not s.sms_verify_enabled and s.info().sms_verify is False
    with pytest.raises(ValidationFailed, match="주문번호"):
        s.guest_send_code(GuestCodeIn(name="김영희", phone="010-7777-1234"))
