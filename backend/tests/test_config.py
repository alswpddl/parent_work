

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
