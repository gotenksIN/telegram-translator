import pytest

from app.settings import get_settings


RELEVANT_ENV = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_API_BASE_URL",
    "GEMINI_API_KEY",
    "GEMINI_API_BASE",
    "GEMINI_MODEL",
    "GEMINI_THINKING_LEVEL",
    "TARGET_LANGUAGE",
    "REQUEST_TIMEOUT_SECONDS",
    "TWITTER_PREVIEW_HOST",
    "YOUTUBE_COOKIES_PATH",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in RELEVANT_ENV:
        monkeypatch.delenv(name, raising=False)


def test_get_settings_loads_required_values_and_defaults(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", " token ")
    monkeypatch.setenv("GEMINI_API_KEY", " key ")

    settings = get_settings()

    assert settings.TELEGRAM_BOT_TOKEN == "token"
    assert settings.GEMINI_API_KEY == "key"
    assert settings.GEMINI_MODEL == "gemini-3.7-flash"
    assert settings.GEMINI_THINKING_LEVEL == "low"
    assert settings.TARGET_LANGUAGE == "English"
    assert settings.REQUEST_TIMEOUT_SECONDS == 10.0
    assert settings.TWITTER_PREVIEW_HOST == "hitlerx.com"
    assert settings.TELEGRAM_API_BASE_URL is None
    assert settings.GEMINI_API_BASE is None
    assert settings.YOUTUBE_COOKIES_PATH is None


@pytest.mark.parametrize("missing", ["TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY"])
def test_get_settings_requires_credentials(monkeypatch, missing):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.delenv(missing)

    with pytest.raises(RuntimeError, match=f"Missing required environment variable: {missing}"):
        get_settings()


def test_get_settings_normalizes_optional_values(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv("TELEGRAM_API_BASE_URL", " https://telegram.example/root/ ")
    monkeypatch.setenv("GEMINI_API_BASE", "http://gemini.example/")
    monkeypatch.setenv("GEMINI_THINKING_LEVEL", " HIGH ")
    monkeypatch.setenv("TWITTER_PREVIEW_HOST", "preview.example:8443")
    monkeypatch.setenv("YOUTUBE_COOKIES_PATH", " cookies.txt ")

    settings = get_settings()

    assert settings.TELEGRAM_API_BASE_URL == "https://telegram.example/root"
    assert settings.GEMINI_API_BASE == "http://gemini.example"
    assert settings.GEMINI_THINKING_LEVEL == "high"
    assert settings.TWITTER_PREVIEW_HOST == "preview.example:8443"
    assert settings.YOUTUBE_COOKIES_PATH == "cookies.txt"


@pytest.mark.parametrize("name", ["GEMINI_MODEL", "TARGET_LANGUAGE", "TWITTER_PREVIEW_HOST"])
def test_get_settings_rejects_empty_defaulted_values(monkeypatch, name):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv(name, "   ")

    with pytest.raises(RuntimeError, match="must not be empty"):
        get_settings()


@pytest.mark.parametrize("value", ["https://example.com", "example.com/path"])
def test_get_settings_rejects_invalid_preview_hosts(monkeypatch, value):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv("TWITTER_PREVIEW_HOST", value)

    with pytest.raises(RuntimeError, match="must be a host name"):
        get_settings()


@pytest.mark.parametrize("name", ["TELEGRAM_API_BASE_URL", "GEMINI_API_BASE"])
@pytest.mark.parametrize("value", ["example.com", "ftp://example.com", "https:///missing-host"])
def test_get_settings_rejects_invalid_http_urls(monkeypatch, name, value):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=r"must be an http\(s\) URL"):
        get_settings()


@pytest.mark.parametrize("value", ["zero", "0", "-1", "nan", "inf"])
def test_get_settings_rejects_invalid_timeouts(monkeypatch, value):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", value)

    with pytest.raises(RuntimeError, match="must be a number|must be greater than zero"):
        get_settings()


def test_get_settings_rejects_unknown_thinking_level(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv("GEMINI_THINKING_LEVEL", "extreme")

    with pytest.raises(RuntimeError, match="must be one of minimal, low, medium, high"):
        get_settings()
