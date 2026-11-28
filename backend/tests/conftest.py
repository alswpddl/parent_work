from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import AppConfig  # noqa: E402
from app.context import bootstrap, build_context  # noqa: E402
from app.core.sheets import MemoryBackend  # noqa: E402
from app.integrations.claude_client import ClaudeClient  # noqa: E402

# 테스트 기준일: 2026-11-18 (수)
BASE_DAY = date(2026, 11, 18)


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(app_env="test", sheets_backend="memory", sheets_cache_ttl=0, seed_demo_data=False)


@pytest.fixture
def backend() -> MemoryBackend:
    return MemoryBackend()


@pytest.fixture
def ctx(config, backend):
    from tests.fixtures import seed_test_basics as seed_basics

    c = build_context(config, backend=backend, claude=ClaudeClient("", "test-model"))
    bootstrap(c)
    seed_basics(c)
    return c


@pytest.fixture
def events(ctx):
    """발행된 이벤트를 모으는 구독자."""
    got: list[tuple[str, dict]] = []
    for name in ("order.created", "order.updated", "order.shipped", "order.unshipped", "order.cancelled"):
        ctx.bus.subscribe(name, lambda payload, n=name: got.append((n, payload)))
    return got


class FakeMessages:
    """anthropic.Anthropic().messages 흉내."""

    def __init__(self, tool_input: dict | None = None, fail_forced_with: int | None = None):
        self.tool_input = tool_input or {}
        self.fail_forced_with = fail_forced_with
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_forced_with and kwargs.get("tool_choice", {}).get("type") == "tool":
            err = Exception("forced tool use not supported")
            err.status_code = self.fail_forced_with  # type: ignore[attr-defined]
            raise err
        block = SimpleNamespace(type="tool_use", name="record_order", input=self.tool_input)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="..."), block])


@pytest.fixture
def fake_anthropic():
    def make(tool_input: dict | None = None, fail_forced_with: int | None = None):
        msgs = FakeMessages(tool_input, fail_forced_with)
        return SimpleNamespace(messages=msgs), msgs

    return make


# ---------------------------------------------------------------------------
# 2~4분기: 모든 모듈 + 가짜 외부 API
# ---------------------------------------------------------------------------
import json  # noqa: E402
from datetime import timedelta  # noqa: E402

from app.integrations.http import HttpResponse  # noqa: E402
from app.integrations.mailer import Mailer  # noqa: E402


class FakeHttp:
    """카카오·솔라피 HTTP 호출을 흉내. self.calls 로 무엇을 보냈는지 확인한다."""

    def __init__(self):
        self.calls: list[dict] = []
        self.overrides: list[tuple] = []  # (url 일부, 응답) — 한 번 쓰면 사라짐

    def queue(self, url_part: str, status: int, body: dict):
        self.overrides.append((url_part, HttpResponse(status, json.dumps(body))))

    def __call__(self, method, url, *, headers=None, form=None, json_body=None, data=None, timeout=15.0):
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "form": form, "json": json_body, "data": data})
        for i, (part, resp) in enumerate(self.overrides):
            if part in url:
                self.overrides.pop(i)
                return resp
        if "kauth.kakao.com/oauth/token" in url:
            return HttpResponse(200, json.dumps({"access_token": "acc-new", "expires_in": 21599, "token_type": "bearer"}))
        if "/v2/user/me" in url:
            return HttpResponse(200, json.dumps({"kakao_account": {"profile": {"nickname": "엄마"}}}))
        if "talk/memo/default/send" in url:
            return HttpResponse(200, json.dumps({"result_code": 0}))
        if "api.solapi.com" in url:
            return HttpResponse(200, json.dumps({"groupInfo": {"groupId": "G1"}, "failedMessageList": []}))
        return HttpResponse(404, "{}")

    def by(self, part: str) -> list[dict]:
        return [c for c in self.calls if part in c["url"]]


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, pw):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture
def http():
    return FakeHttp()


@pytest.fixture
def full_ctx(http):
    from app.config import ALL_MODULES
    from app.core.timeutil import now
    from tests.fixtures import seed_test_basics as seed_basics
    from app.modules import load_modules, register_without_app

    FakeSMTP.sent = []
    cfg = AppConfig(
        app_env="test", sheets_backend="memory", sheets_cache_ttl=0, seed_demo_data=False,
        public_web_url="https://app.example.com", public_api_url="https://api.example.com",
        kakao_rest_api_key="kakao-key", solapi_api_key="sk", solapi_api_secret="ss", solapi_pfid="PF1",
        solapi_sender="0310000000", solapi_tpl_parcel="TPL_P", solapi_tpl_truck="TPL_T",
        solapi_tpl_statement="TPL_S", auth_secret="s" * 40,
        allow_password_signup=True,  # 예전 회원 기능 테스트용 (운영은 닫힘)
    )
    mailer = Mailer(host="smtp.test", port=465, user="u@test.com", password="pw", smtp_factory=FakeSMTP)
    c = build_context(cfg, backend=MemoryBackend(), claude=ClaudeClient("", "m"), http=http, mailer=mailer)
    specs = load_modules(ALL_MODULES)
    c.enabled_modules = [s.name for s in specs]
    register_without_app(specs, c)
    bootstrap(c)
    seed_basics(c)
    # 카카오가 이미 연결된 상태로 시작
    t = now()
    c.tokens.set_many({
        "kakao_access_token": ("acc-1", t + timedelta(hours=5)),
        "kakao_refresh_token": ("ref-1", t + timedelta(days=50)),
    })
    return c
