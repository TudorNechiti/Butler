import pytest
from pydantic import SecretStr, ValidationError

from agents.job_scout.config import Company, JobScoutSettings


def _settings(**overrides: object) -> JobScoutSettings:
    values: dict[str, object] = {
        "telegram_bot_token": SecretStr("t"),
        "telegram_chat_id": "1",
        "anthropic_api_key": SecretStr("k"),
        "job_profile": SecretStr("Backend developer."),
    }
    return JobScoutSettings(_env_file=None, **{**values, **overrides})  # type: ignore[arg-type,call-arg]


def test_adzuna_key_must_come_in_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY"):
        monkeypatch.delenv(name, raising=False)

    assert _settings().adzuna_app_id is None
    assert _settings(adzuna_app_id="id", adzuna_app_key=SecretStr("key")).adzuna_app_id == "id"
    with pytest.raises(ValidationError):
        _settings(adzuna_app_id="id")


def test_validation_errors_do_not_echo_the_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        _settings(job_profile=SecretStr("PRIVATE-PROFILE"), adzuna_app_id="id")
    assert "PRIVATE-PROFILE" not in str(excinfo.value)


@pytest.mark.parametrize("slug", ["Acme", "acme/../x", "acme.evil.example", ""])
def test_company_slug_must_be_url_safe(slug: str) -> None:
    with pytest.raises(ValidationError):
        Company(name="Acme", system="greenhouse", slug=slug)
