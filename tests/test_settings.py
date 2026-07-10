import pytest

from app.settings import get_settings


ENV_KEYS = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_API_BASE_URL",
    "GEMINI_API_KEY",
    "GEMINI_API_BASE",
    "GEMINI_MODEL",
    "TARGET_LANGUAGE",
    "REQUEST_TIMEOUT_SECONDS",
    "TWITTER_PREVIEW_HOST",
    "YOUTUBE_COOKIES_PATH",
)


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")


def test_get_settings_uses_valid_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_env(monkeypatch)

    settings = get_settings()

    assert settings.GEMINI_MODEL == "gemini-3.5-flash"
    assert settings.TARGET_LANGUAGE == "English"
    assert settings.REQUEST_TIMEOUT_SECONDS == 10
    assert settings.TWITTER_PREVIEW_HOST == "hitlerx.com"


def test_get_settings_rejects_invalid_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "0")

    with pytest.raises(RuntimeError, match="greater than zero"):
        get_settings()


def test_get_settings_rejects_empty_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv("GEMINI_MODEL", " ")

    with pytest.raises(RuntimeError, match="GEMINI_MODEL"):
        get_settings()


def test_get_settings_rejects_preview_host_with_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv("TWITTER_PREVIEW_HOST", "https://preview.example")

    with pytest.raises(RuntimeError, match="host name without a scheme"):
        get_settings()
