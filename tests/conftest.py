from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        TELEGRAM_BOT_TOKEN="token",
        TELEGRAM_API_BASE_URL=None,
        GEMINI_API_KEY="key",
        GEMINI_API_BASE=None,
        GEMINI_MODEL="model",
        GEMINI_THINKING_LEVEL="low",
        TARGET_LANGUAGE="English",
        REQUEST_TIMEOUT_SECONDS=10.0,
        TWITTER_PREVIEW_HOST="preview.example",
        YOUTUBE_COOKIES_PATH=None,
    )


@pytest.fixture
def command_objects(settings):
    message = SimpleNamespace(reply_to_message=None, reply_text=AsyncMock())
    chat = SimpleNamespace(id=123)
    bot = SimpleNamespace(id=999, send_chat_action=AsyncMock())
    application = SimpleNamespace(bot_data={"settings": settings})
    context = SimpleNamespace(bot=bot, application=application)
    update = SimpleNamespace(effective_message=message, effective_chat=chat)
    return update, context, message, bot
