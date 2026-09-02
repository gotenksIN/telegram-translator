from __future__ import annotations

import logging
from asyncio import wait_for

from google.genai import Client, types
from pydantic import BaseModel, Field, ValidationError

from app.settings import Settings

logger = logging.getLogger(__name__)

_client: Client | None = None


class TranslationResponse(BaseModel):
    translated_text: str = Field(description="The translated text.")
    source_language: str = Field(
        description="The full, capitalized English name of the original language of the text (e.g., 'Chinese', 'Japanese', 'Spanish', 'English'). If the text is already in the target language, still identify its language correctly."
    )


def get_client(settings: Settings) -> Client:
    global _client
    if _client is None:
        _client = Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                base_url=settings.GEMINI_API_BASE,
                timeout=int(settings.REQUEST_TIMEOUT_SECONDS * 1000),
            ),
        )
    return _client


async def aclose_client() -> None:
    global _client
    if _client is not None:
        await _client.aio.aclose()
        _client = None


def build_content_config(settings: Settings) -> types.GenerateContentConfig:
    thinking_config = (
        types.ThinkingConfig(thinking_level=settings.GEMINI_THINKING_LEVEL.upper())
        if settings.GEMINI_THINKING_LEVEL is not None
        else None
    )
    system_instruction = f"""
Translate input into {settings.TARGET_LANGUAGE}.

Rules:
- Preserve handles, hashtags, names, URLs, emojis, and line breaks.
- Produce a concise, natural translation that preserves the original meaning, tone, humor, slang, and rhetorical effect; do not translate so literally that these are lost.
- Handle wordplay in any language by recreating it naturally in the target language when possible.
- Whenever the text contains wordplay, a pun, or cultural or linguistic context that is not obvious from the translation alone, append one brief translator's note in {settings.TARGET_LANGUAGE}. Explain only what is needed to understand the original text. Label it "Translator's note:" and place it after the translated text. Do not add any other commentary.
- If the text is already in {settings.TARGET_LANGUAGE}, return it unchanged.
""".strip()
    return types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=TranslationResponse,
        thinking_config=thinking_config,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        system_instruction=system_instruction,
    )


async def translate_text(text: str, settings: Settings, *, source_type: str = "tweet") -> dict[str, str]:
    client = get_client(settings)
    source_label = (
        "message" if source_type == "message" else "Twitter/X post" if source_type == "tweet" else "web page preview"
    )
    contents = f"Translate this {source_label}:\n\n{text}"

    response = await wait_for(
        client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=build_content_config(settings),
        ),
        settings.REQUEST_TIMEOUT_SECONDS,
    )

    parsed: TranslationResponse | None = response.parsed
    if parsed is None:
        candidates = getattr(response, "candidates", None) or []
        finish_reasons = [
            getattr(c, "finish_reason", None) for c in candidates if getattr(c, "finish_reason", None) is not None
        ]
        text_content: str | None = None
        try:
            text_content = getattr(response, "text", None)
        except (AttributeError, ValueError):
            text_content = None
        validation_error: str | None = None
        if text_content:
            try:
                TranslationResponse.model_validate_json(text_content)
            except ValidationError as exc:
                validation_error = str(exc)
        logger.warning(
            "Gemini response missing parsed output (finish_reasons=%s, validation_error=%s)",
            finish_reasons,
            validation_error,
        )
        raise ValueError("No valid parsed JSON response from Gemini")

    return {
        "translated_text": parsed.translated_text.strip(),
        "source_language": parsed.source_language.strip(),
    }
