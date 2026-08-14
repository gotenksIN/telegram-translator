import os
from dataclasses import dataclass
from math import isfinite
from urllib.parse import urlparse

from dotenv import load_dotenv


load_dotenv()

THINKING_LEVELS = ("minimal", "low", "medium", "high")


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_env(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None


def _choice_env(name: str, choices: tuple[str, ...], default: str) -> str:
    value = os.environ.get(name, default).strip().lower()
    if value not in choices:
        raise RuntimeError(f"Environment variable must be one of {', '.join(choices)}: {name}")
    return value


def _env_with_default(name: str, default: str) -> str:
    value = os.environ.get(name, default).strip()
    if not value:
        raise RuntimeError(f"Environment variable must not be empty: {name}")
    return value


def _optional_http_url_env(name: str) -> str | None:
    value = _optional_env(name)
    if value is None:
        return None

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"Environment variable must be an http(s) URL: {name}")
    return value.rstrip("/")


def _host_env(name: str, default: str) -> str:
    value = _env_with_default(name, default)
    parsed = urlparse(f"//{value}")
    if parsed.netloc != value or not parsed.hostname:
        raise RuntimeError(f"Environment variable must be a host name without a scheme or path: {name}")
    return value


def _positive_float_env(name: str, default: str) -> float:
    value = os.environ.get(name, default).strip()
    try:
        parsed = float(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable must be a number: {name}") from exc

    if not isfinite(parsed) or parsed <= 0:
        raise RuntimeError(f"Environment variable must be greater than zero: {name}")
    return parsed


@dataclass(frozen=True)
class Settings:
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_API_BASE_URL: str | None
    GEMINI_API_KEY: str
    GEMINI_API_BASE: str | None
    GEMINI_MODEL: str
    GEMINI_THINKING_LEVEL: str
    TARGET_LANGUAGE: str
    REQUEST_TIMEOUT_SECONDS: float
    TWITTER_PREVIEW_HOST: str
    YOUTUBE_COOKIES_PATH: str | None


def get_settings() -> Settings:
    return Settings(
        TELEGRAM_BOT_TOKEN=_required_env("TELEGRAM_BOT_TOKEN"),
        TELEGRAM_API_BASE_URL=_optional_http_url_env("TELEGRAM_API_BASE_URL"),
        GEMINI_API_KEY=_required_env("GEMINI_API_KEY"),
        GEMINI_API_BASE=_optional_http_url_env("GEMINI_API_BASE"),
        GEMINI_MODEL=_env_with_default("GEMINI_MODEL", "gemini-3.7-flash"),
        GEMINI_THINKING_LEVEL=_choice_env("GEMINI_THINKING_LEVEL", THINKING_LEVELS, "low"),
        TARGET_LANGUAGE=_env_with_default("TARGET_LANGUAGE", "English"),
        REQUEST_TIMEOUT_SECONDS=_positive_float_env("REQUEST_TIMEOUT_SECONDS", "10"),
        TWITTER_PREVIEW_HOST=_host_env("TWITTER_PREVIEW_HOST", "hitlerx.com"),
        YOUTUBE_COOKIES_PATH=_optional_env("YOUTUBE_COOKIES_PATH"),
    )
