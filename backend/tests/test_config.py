

def test_sheet_id_accepts_full_url():
    from app.config import sheet_id

    url = "https://docs.google.com/spreadsheets/d/1AbC-dEf_123/edit#gid=0"
    assert sheet_id(url) == "1AbC-dEf_123"
    assert sheet_id(" 1AbC-dEf_123 ") == "1AbC-dEf_123"
    assert sheet_id("") == ""


def test_bad_service_account_json_has_clear_message(monkeypatch):
    import pytest

    from app.config import AppConfig

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"type": "service_account", ')
    with pytest.raises(RuntimeError, match="붙여넣었는지"):
        AppConfig.from_env()


def test_social_login_keys_from_env(monkeypatch):
    from app.config import AppConfig

    for k, v in {"NAVER_CLIENT_ID": "n1", "NAVER_CLIENT_SECRET": "n2", "APPLE_CLIENT_ID": "a1",
                 "APPLE_TEAM_ID": "a2", "APPLE_KEY_ID": "a3", "APPLE_PRIVATE_KEY": "a4"}.items():
        monkeypatch.setenv(k, v)
    c = AppConfig.from_env()
    assert (c.naver_client_id, c.naver_client_secret) == ("n1", "n2")
    assert (c.apple_client_id, c.apple_team_id, c.apple_key_id, c.apple_private_key) == ("a1", "a2", "a3", "a4")
