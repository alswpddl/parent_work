"""HTTP 레벨 테스트 — FastAPI 가 설치된 환경(Codespaces 등)에서 실행된다."""

from __future__ import annotations

from io import BytesIO

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.core.sheets import MemoryBackend  # noqa: E402
from app.integrations.claude_client import ClaudeClient  # noqa: E402
from app.main import create_app  # noqa: E402

from .test_parser_and_matching import SAMPLE  # noqa: E402


@pytest.fixture
def client():
    cfg = AppConfig(
        app_env="test", sheets_backend="memory", sheets_cache_ttl=0, admin_pin="2580", auth_secret="x" * 40,
        seed_demo_data=False, allow_password_signup=True,  # 예전 회원 기능 테스트용 (운영은 닫힘)
    )
    app = create_app(cfg, backend=MemoryBackend(), claude=ClaudeClient("", "m"))
    with TestClient(app) as c:
        from tests.fixtures import seed_test_basics as seed_basics

        seed_basics(app.state.ctx)
        tok = c.post("/api/auth/pin", json={"pin": "2580"}).json()["token"]
        c.headers.update({"Authorization": f"Bearer {tok}"})
        yield c


def test_health_and_features(client):
    assert client.get("/api/health").json()["ok"] is True
    f = client.get("/api/system/features").json()
    assert [m["name"] for m in f["modules"]][:3] == ["q1_masters", "q1_orders", "q1_shipping"]
    assert len(f["modules"]) == 13
    assert f["ai_parser"] is False and f["auth_required"] is True


def test_auth_required():
    cfg = AppConfig(app_env="test", admin_pin="2580", auth_secret="x" * 40)
    app = create_app(cfg, backend=MemoryBackend(), claude=ClaudeClient("", "m"))
    with TestClient(app) as c:
        r = c.get("/api/orders")
        assert r.status_code == 401 and r.json()["error"] == "unauthorized"
        assert c.post("/api/auth/pin", json={"pin": "0000"}).status_code == 401


def test_full_q1_flow(client):
    draft = client.post("/api/orders/parse", json={"text": SAMPLE}).json()
    assert draft["parser"] == "rule" and draft["customer"]["customer_id"] == "C0001"
    items = [{"sku": i["sku"], "qty": i["qty"]} for i in draft["items"]]

    r = client.post(
        "/api/orders",
        json={"customer_id": "C0001", "items": items, "due_date": draft["due_date"], "note": draft["note"], "raw_text": SAMPLE},
    )
    assert r.status_code == 201, r.text
    order = r.json()
    oid = order["order_id"]
    assert order["ship_method"] == "택배"

    big = client.post("/api/orders", json={"customer_id": "C0001", "items": [{"sku": "CHI-10KG", "qty": 6}]}).json()
    assert big["ship_method"] == "화물"

    board = client.get("/api/shipping/board").json()
    assert [o["order_id"] for o in board["parcel"]] == [oid]
    assert [o["order_id"] for o in board["truck"]] == [big["order_id"]]

    x = client.post("/api/shipping/parcel-export", json={})
    assert x.status_code == 200 and x.headers["x-order-count"] == "1"
    ws = load_workbook(BytesIO(x.content)).active
    assert ws.max_row == 2

    t = client.get(f"/api/shipping/{big['order_id']}/dispatch-text").json()["text"]
    assert "[화물 배차 요청]" in t

    shipped = client.post(f"/api/shipping/{oid}/ship").json()
    assert shipped["status"] == "출고완료"
    assert len(client.get("/api/shipping/board").json()["parcel"]) == 0

    summary = client.get("/api/production/summary").json()
    assert summary["truck_count"] == 1 and summary["parcel_count"] == 0


def test_validation_message_is_korean(client):
    r = client.post("/api/orders", json={"customer_id": "C0001", "items": []})
    assert r.status_code == 422 and "품목" in r.json()["message"]


def test_masters_crud(client):
    c = client.post("/api/customers", json={"name": "새마을식당", "phone": "010-7777-8888"}).json()
    assert c["customer_id"] == "C0003"
    assert client.post("/api/customers", json={"name": "새마을식당"}).status_code == 422
    c = client.patch(f"/api/customers/{c['customer_id']}", json={"active": False}).json()
    assert c["active"] is False
    assert all(x["name"] != "새마을식당" for x in client.get("/api/customers").json())

    p = client.post("/api/products", json={"name": "참깨", "spec": "1kg", "unit_kg": 1.05}).json()
    assert p["sku"] == "P0001"
    s = client.put("/api/settings", json={"threshold_kg": 70}).json()
    assert s["threshold_kg"] == 70


def test_job_endpoint_requires_secret():
    cfg = AppConfig(app_env="test", job_secret="j" * 20)
    app = create_app(cfg, backend=MemoryBackend(), claude=ClaudeClient("", "m"))
    app.state.ctx.jobs.register("ping", lambda ctx: {"pong": True})
    with TestClient(app) as c:
        assert c.post("/api/jobs/ping").status_code == 401
        assert c.post("/api/jobs/ping", headers={"X-Job-Secret": "j" * 20}).json() == {"ok": True, "pong": True}


# ---------------------------------------------------------------- 2~4분기 HTTP
def _xlsx(rows):
    from openpyxl import Workbook

    wb = Workbook()
    for r in rows:
        wb.active.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_public_self_order_flow(client):
    link = client.post("/api/customers/C0001/order-link").json()
    token = link["token"]
    public = TestClient(client.app)  # 로그인 없이
    form = public.get(f"/api/public/order-form/{token}").json()
    assert form["customer_name"] == "한솥식당"
    r = public.post(f"/api/public/orders/{token}", json={"items": [{"sku": "SES-18L", "qty": 2}]})
    assert r.status_code == 201, r.text
    assert public.get(f"/api/public/orders/{token}").json()[0]["order_id"] == r.json()["order_id"]
    assert public.get("/api/public/order-form/" + "x" * 24).status_code == 404


def test_tracking_upload_and_settlement_pdf(client):
    o = client.post("/api/orders", json={"customer_id": "C0001", "items": [{"sku": "SES-18L", "qty": 1}]}).json()
    data = _xlsx([["받는분", "운송장번호", "주문번호"], ["김사장", "123456789012", o["order_id"]]])
    p = client.post(
        "/api/tracking/import",
        files={"file": ("t.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"carrier": "CJ대한통운"},
    ).json()
    assert p["matched"] == 1
    r = client.post(f"/api/tracking/import/{p['import_id']}/confirm", json={"carrier": "CJ대한통운"}).json()
    assert r["registered"] == 1

    from app.core.timeutil import today
    from app.modules.q4_settlement.service import prev_period

    period = f"{today():%Y-%m}"
    g = client.post("/api/settlements/generate", json={"period": period}).json()
    sid = g["settlements"][0]["settlement_id"]
    pdf = client.get(f"/api/settlements/{sid}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    url = client.get(f"/api/settlements/{sid}/link").json()["url"]
    token = url.rsplit("/", 1)[1]
    assert TestClient(client.app).get(f"/api/public/statements/{token}").status_code == 200
    assert prev_period(today())


def test_inventory_reorder_briefing_endpoints(client):
    assert len(client.get("/api/inventory").json()) == 9
    assert client.get("/api/reorder/stats").status_code == 200
    b = client.get("/api/briefing/preview").json()
    assert b["text"].startswith("🏭")
    st = client.get("/api/integrations/kakao/status").json()
    assert st["configured"] is False and st["redirect_uri"].endswith("/api/integrations/kakao/callback")
    assert client.get("/api/system/status").json()["integration_warnings"]


def test_kakao_callback_rejects_bad_state(client):
    r = TestClient(client.app).get("/api/integrations/kakao/callback?code=x&state=bad", follow_redirects=False)
    assert r.status_code in (302, 307) and "kakao=fail" in r.headers["location"]


def test_public_web_order_flow(client):
    public = TestClient(client.app)  # 로그인 없이
    info = public.get("/api/public/shop").json()
    assert info["products"] and "개인정보" in info["privacy_text"]
    body = {
        "name": "김영희", "phone": "010-7777-8888", "address": "서울시 마포구 월드컵로 1",
        "items": [{"sku": "SES-18L", "qty": 2}], "agree_privacy": True,
    }
    r = public.post("/api/public/shop/orders", json=body, headers={"X-Forwarded-For": "5.5.5.5"})
    assert r.status_code == 201, r.text
    oid = r.json()["order_id"]
    look = public.get("/api/public/shop/orders/lookup", params={"order_id": oid, "phone4": "8888"})
    assert look.status_code == 200 and look.json()["order_id"] == oid
    assert public.get("/api/public/shop/orders/lookup", params={"order_id": oid, "phone4": "0000"}).status_code == 404
    bad = public.post("/api/public/shop/orders", json={**body, "agree_privacy": False})
    assert bad.status_code == 422
    # 관리자 쪽에서는 웹주문서 경로로 보인다
    orders = client.get("/api/orders").json()["orders"]
    assert any(o["order_id"] == oid and o["source"] == "웹주문서" for o in orders)


def test_status_shows_google_info_without_secrets(client):
    st = client.get("/api/system/status").json()
    assert st["google"]["connected"] is False and "private_key" not in str(st)
    r = client.post("/api/system/google/check").json()
    assert r["ok"] is False and "메모리" in r["message"]


def test_shop_account_http_flow(client):
    public = TestClient(client.app)
    body = {"name": "김영희", "phone": "010-7777-8888", "password": "1234", "agree_privacy": True}
    r = public.post("/api/public/shop/auth/signup", json=body)
    assert r.status_code == 201, r.text
    tok = r.json()["token"]
    assert public.get("/api/public/shop/me").status_code == 401
    h = {"X-Shop-Token": tok}
    assert public.get("/api/public/shop/me", headers=h).json()["name"] == "김영희"
    o = public.post("/api/public/shop/orders", headers=h, json={
        "name": "김영희", "phone": "010-7777-8888", "address": "서울시 마포구 1",
        "items": [{"sku": "SES-18L", "qty": 1}], "agree_privacy": True,
    })
    assert o.status_code == 201
    assert public.get("/api/public/shop/me/orders", headers=h).json()[0]["order_id"] == o.json()["order_id"]
    cid = next(c["customer_id"] for c in client.get("/api/customers").json() if c["phone"] == "010-7777-8888")
    assert client.post(f"/api/customers/{cid}/reset-web-password").json()["has_web_account"] is False
    assert public.get("/api/public/shop/me", headers=h).status_code == 401


def test_kakao_skill_requires_key(client):
    body = {"userRequest": {"utterance": "택배비", "user": {"id": "x"}}}
    assert client.post("/api/kakao/skill", json=body).status_code == 404  # 키가 없으면 꺼져 있음
    client.app.state.ctx.config.kakao_skill_key = "s3cret"
    assert client.post("/api/kakao/skill?key=wrong", json=body).status_code == 404
    r = client.post("/api/kakao/skill?key=s3cret", json=body)
    assert r.status_code == 200 and r.json()["version"] == "2.0"
    assert client.get("/api/system/status").json()["kakao_bot"]["skill_url"].endswith("/api/kakao/skill?key=s3cret")


def test_push_api(client):
    from tests.test_webpush import Phone

    phone = Phone()
    st = client.post("/api/push/status", json={"endpoint": phone.endpoint}).json()
    assert st["devices"] == 0 and st["subscribed"] is False and len(st["public_key"]) > 80
    r = client.post("/api/push/subscribe", json={"endpoint": phone.endpoint, "keys": phone.keys, "label": "아버지 폰"})
    assert r.status_code == 200 and r.json()["subscribed"] is True
    assert client.post("/api/push/status", json={"endpoint": phone.endpoint}).json()["devices"] == 1
    assert client.post("/api/push/unsubscribe", json={"endpoint": phone.endpoint}).json()["devices"] == 0
    bad = client.post("/api/push/subscribe", json={"endpoint": "http://x.example/aaaaaaaa", "keys": phone.keys})
    assert bad.status_code == 422


def test_product_image_upload_and_public_get(client):
    import base64 as _b64

    prods = client.get("/api/products").json()
    p = prods[0] if isinstance(prods, list) else prods["products"][0]
    raw = b"\xff\xd8\xff" + b"jpegdata" * 100
    r = client.post(f"/api/products/{p['sku']}/image", json={"data_url": "data:image/jpeg;base64," + _b64.b64encode(raw).decode()})
    assert r.status_code == 200, r.text
    url = r.json()[0]["image_url"]
    path = url.split("://", 1)[1].split("/", 1)[1]
    img = TestClient(client.app).get("/" + path)  # 로그인 없이
    assert img.status_code == 200 and img.content == raw and img.headers["content-type"] == "image/jpeg"
    assert "immutable" in img.headers["cache-control"]
    # 사진 빼기
    assert client.post(f"/api/products/{p['sku']}/image", json={"data_url": ""}).json()[0]["image_url"] == ""


def test_delivered_routes(client):
    r = client.post("/api/shipping/NOPE-0000/delivered")
    assert r.status_code in (404, 422)
    pub = TestClient(client.app).post("/api/public/shop/orders/received", json={"order_id": "NOPE-0000", "phone4": "1234"})
    assert pub.status_code in (404, 422)
def test_apple_callback_form_post(client):
    r = TestClient(client.app).post("/api/public/shop/auth/apple/callback", data={"error": "user_cancelled_authorize"}, follow_redirects=False)
    assert r.status_code == 303 and "kerr=" in r.headers["location"] and "p=apple" in r.headers["location"]
    r = TestClient(client.app).get("/api/public/shop/auth/naver/start", follow_redirects=False)
    assert r.status_code == 302 and "kerr=" in r.headers["location"]
