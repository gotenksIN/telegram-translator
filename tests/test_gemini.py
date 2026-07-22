from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.gemini as gemini
from app.gemini import TranslationResponse


@pytest.fixture(autouse=True)
def reset_client(monkeypatch):
    monkeypatch.setattr(gemini, "_client", None)


def test_get_client_builds_and_caches_default_client(monkeypatch, settings):
    client = object()
    constructor = Mock(return_value=client)
    monkeypatch.setattr(gemini, "Client", constructor)

    assert gemini.get_client(settings) is client
    assert gemini.get_client(settings) is client
    constructor.assert_called_once_with(api_key="key")


def test_get_client_configures_custom_base_url(monkeypatch, settings):
    settings = settings.__class__(**{**settings.__dict__, "GEMINI_API_BASE": "https://proxy.example"})
    constructor = Mock(return_value=object())
    monkeypatch.setattr(gemini, "Client", constructor)

    gemini.get_client(settings)

    assert constructor.call_args.kwargs["api_key"] == "key"
    assert constructor.call_args.kwargs["http_options"].base_url == "https://proxy.example"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_type", "source_label"),
    [("message", "message"), ("tweet", "Twitter/X post"), ("preview", "web page preview")],
)
async def test_translate_text_builds_request_and_returns_trimmed_result(monkeypatch, settings, source_type, source_label):
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
    assert f"Translate this {source_label} into English." in kwargs["contents"]
    assert kwargs["contents"].endswith("Text:\noriginal")
    assert kwargs["config"].temperature == 0.0
    assert kwargs["config"].response_schema is TranslationResponse
    assert kwargs["config"].thinking_config.thinking_level == "LOW"


@pytest.mark.asyncio
async def test_translate_text_rejects_missing_parsed_response(monkeypatch, settings):
    generate_content = AsyncMock(return_value=SimpleNamespace(parsed=None))
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(gemini, "get_client", Mock(return_value=client))

    with pytest.raises(ValueError, match="No valid parsed JSON response"):
        await gemini.translate_text("original", settings)
