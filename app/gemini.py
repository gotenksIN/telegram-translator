from __future__ import annotations

from asyncio import wait_for

from google.genai import Client, types
from pydantic import BaseModel, Field

from app.settings import Settings

_client: Client | None = None


class TranslationResponse(BaseModel):
    translated_text: str = Field(description="The translated text.")
    source_language: str = Field(
        description="The full, capitalized English name of the original language of the text (e.g., 'Chinese', 'Japanese', 'Spanish', 'English'). If the text is already in the target language, still identify its language correctly."
    )


def get_client(settings: Settings) -> Client:
    global _client
    if _client is None:
        if settings.GEMINI_API_BASE:
            _client = Client(
                api_key=settings.GEMINI_API_KEY,
                http_options=types.HttpOptions(base_url=settings.GEMINI_API_BASE),
            )
        else:
            _client = Client(api_key=settings.GEMINI_API_KEY)
    return _client


def build_content_config(settings: Settings) -> types.GenerateContentConfig:
    thinking_config = (
        types.ThinkingConfig(thinking_level=settings.GEMINI_THINKING_LEVEL.upper())
        if settings.GEMINI_THINKING_LEVEL is not None
        else None
    )
    return types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=TranslationResponse,
        thinking_config=thinking_config,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


async def translate_text(text: str, settings: Settings, *, source_type: str = "tweet") -> dict[str, str]:
    client = get_client(settings)
    source_label = (
        "message" if source_type == "message" else "Twitter/X post" if source_type == "tweet" else "web page preview"
    )
    prompt = f"""
Translate this {source_label} into {settings.TARGET_LANGUAGE}.

Rules:
- Preserve handles, hashtags, names, URLs, emojis, and line breaks.
- Produce a concise, natural translation that preserves the original meaning, tone, humor, slang, and rhetorical effect; do not translate so literally that these are lost.
- Handle wordplay in any language by recreating it naturally in the target language when possible.
- Whenever the text contains wordplay, a pun, or cultural or linguistic context that is not obvious from the translation alone, append one brief translator's note in {settings.TARGET_LANGUAGE}. Explain only what is needed to understand the original text. Label it "Translator's note:" and place it after the translated text. Do not add any other commentary.
- If the text is already in {settings.TARGET_LANGUAGE}, return it unchanged.

Text:
{text}
""".strip()

    response = await wait_for(
        client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=build_content_config(settings),
        ),
        settings.REQUEST_TIMEOUT_SECONDS,
    )

    parsed: TranslationResponse | None = response.parsed
    if not parsed:
        raise ValueError("No valid parsed JSON response from Gemini")

    return {
        "translated_text": parsed.translated_text.strip(),
        "source_language": parsed.source_language.strip(),
    }
