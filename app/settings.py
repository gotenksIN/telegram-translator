import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_API_BASE_URL: str | None
    GEMINI_API_KEY: str
    GEMINI_API_BASE: str | None
    GEMINI_MODEL: str
    TARGET_LANGUAGE: str
    REQUEST_TIMEOUT_SECONDS: float
    YOUTUBE_COOKIES_PATH: str | None


def get_settings() -> Settings:
    return Settings(
        TELEGRAM_BOT_TOKEN=_required_env("TELEGRAM_BOT_TOKEN"),
        TELEGRAM_API_BASE_URL=os.environ.get("TELEGRAM_API_BASE_URL") or None,
        GEMINI_API_KEY=_required_env("GEMINI_API_KEY"),
        GEMINI_API_BASE=os.environ.get("GEMINI_API_BASE") or None,
        GEMINI_MODEL=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
        TARGET_LANGUAGE=os.environ.get("TARGET_LANGUAGE", "English"),
        REQUEST_TIMEOUT_SECONDS=float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "10")),
        YOUTUBE_COOKIES_PATH=os.environ.get("YOUTUBE_COOKIES_PATH") or None,
    )
