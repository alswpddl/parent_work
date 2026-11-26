from __future__ import annotations

import pytest

from app.config import AppConfig
from app.core.auth import LoginLimiter, check_job_secret, check_pin, issue_admin_token, verify_admin_token
from app.core.errors import TooManyRequests, UnauthorizedError
from app.core.ids import next_order_id, next_seq_id
from app.core.jobs import JobRegistry
from app.schemas.settings import SettingsPatch

from .conftest import BASE_DAY


def test_settings_defaults_and_save(ctx, backend):
    st = ctx.settings.load()
    assert st.threshold_kg == 50 and st.factory_name == "예시공장"
    st = ctx.settings.save(SettingsPatch(threshold_kg=80))
    assert st.threshold_kg == 80
    keys = [r[0] for r in backend.tabs["_설정"][1:]]
    assert keys.count("threshold_kg") == 1


def test_bad_setting_value_falls_back(ctx, backend):
    header = backend.tabs["_설정"][0]
    for r in backend.tabs["_설정"][1:]:
        if r[0] == "pallet_kg":
            r[header.index("값")] = "많이"
    assert ctx.settings.load().pallet_kg == 600


def test_ids():
    import re

    oid = next_order_id(["O-20261118-001"], BASE_DAY)
    assert re.fullmatch(r"20261118-[2-9A-HJKMNP-Z]{4}", oid)
    assert len({next_order_id([], BASE_DAY) for _ in range(50)}) > 40  # 매번 다른 번호
    assert next_seq_id(["C0001", "C0010", "X"], "C") == "C0011"


def test_token_roundtrip():
    tok, _ = issue_admin_token("s" * 40, 1)
    assert verify_admin_token("s" * 40, tok)["role"] == "admin"
    with pytest.raises(UnauthorizedError):
        verify_admin_token("t" * 40, tok)


def test_pin_and_job_secret():
    assert check_pin("1234", "1234") and not check_pin("1234", "1235") and not check_pin("", "")
    assert check_job_secret("abc", "abc") and not check_job_secret("abc", None) and not check_job_secret("", "")


def test_login_limiter():
    lim = LoginLimiter(max_attempts=2, window_sec=60)
    lim.check("ip")
    lim.fail("ip")
    lim.fail("ip")
    with pytest.raises(TooManyRequests):
        lim.check("ip")
    lim.reset("ip")
    lim.check("ip")


def test_job_registry():
    reg = JobRegistry()
    reg.register("hello", lambda ctx: {"n": 1}, cron="0 8 * * *")
    assert reg.run("hello", None) == {"ok": True, "n": 1}
    with pytest.raises(ValueError):
        reg.register("hello", lambda c: {})


def test_production_config_check():
    bad = AppConfig(app_env="prod")
    assert len(bad.check_production()) >= 4
    assert AppConfig(app_env="dev").check_production() == []
