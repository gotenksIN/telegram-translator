from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.gemini as gemini
from app.gemini import TranslationResponse
from app.settings import get_settings


@pytest.mark.anyio
async def test_translate_text_configures_thinking_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    settings = replace(get_settings(), GEMINI_THINKING_LEVEL="low")
    generate_content = AsyncMock(
        return_value=SimpleNamespace(parsed=TranslationResponse(translated_text="Hello", source_language="Korean"))
    )
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(gemini, "get_client", lambda _: client)

    await gemini.translate_text("안녕하세요", settings)

    config = generate_content.await_args.kwargs["config"]
    assert config.thinking_config.thinking_level.value == "LOW"
    assert config.thinking_config.thinking_budget is None


@pytest.mark.anyio
async def test_translate_text_omits_thinking_config_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    settings = replace(get_settings(), GEMINI_THINKING_LEVEL=None)
    generate_content = AsyncMock(
        return_value=SimpleNamespace(parsed=TranslationResponse(translated_text="Hello", source_language="Korean"))
    )
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(gemini, "get_client", lambda _: client)

    await gemini.translate_text("안녕하세요", settings)

    assert generate_content.await_args.kwargs["config"].thinking_config is None
