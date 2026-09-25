from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app import gemini
from app.gemini import TranslationResponse


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_type",
    ["message", "tweet", "preview"],
)
async def test_translate_text_translates_message_into_target_language(monkeypatch, settings, source_type):
    generate_content = AsyncMock(
        return_value=SimpleNamespace(
            parsed=TranslationResponse(translated_text=" translated ", source_language=" Japanese ")
        )
    )
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(gemini, "get_client", Mock(return_value=client))

    result = await gemini.translate_text("original", settings, source_type=source_type)

    assert result == {"translated_text": "translated", "source_language": "Japanese"}
    kwargs = generate_content.call_args.kwargs
    assert kwargs["model"] == "model"
    assert kwargs["config"].automatic_function_calling.disable is True
    assert kwargs["config"].temperature == 0.0
    assert kwargs["config"].response_mime_type == "application/json"
    assert kwargs["config"].response_schema is TranslationResponse
    assert kwargs["config"].thinking_config.thinking_level == "LOW"


@pytest.mark.asyncio
async def test_translate_text_rejects_missing_parsed_response(monkeypatch, settings):
    generate_content = AsyncMock(return_value=SimpleNamespace(parsed=None))
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(gemini, "get_client", Mock(return_value=client))

    with pytest.raises(ValueError, match="No valid parsed JSON response from Gemini"):
        await gemini.translate_text("original", settings)


@pytest.mark.asyncio
async def test_aclose_client_closes_underlying_client(monkeypatch):
    mock_aclose = AsyncMock()
    mock_client = SimpleNamespace(aio=SimpleNamespace(aclose=mock_aclose))
    monkeypatch.setattr(gemini, "_client", mock_client)

    await gemini.aclose_client()
    mock_aclose.assert_awaited_once()

    await gemini.aclose_client()
    mock_aclose.assert_awaited_once()
