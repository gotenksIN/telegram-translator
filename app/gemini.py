from __future__ import annotations

from google.genai import Client, types

from app.settings import Settings


_client: Client | None = None


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


async def translate_text(text: str, settings: Settings, *, source_type: str = "tweet") -> str:
    client = get_client(settings)
    source_label = "message" if source_type == "message" else "Twitter/X post" if source_type == "tweet" else "web page preview"
    prompt = f"""
Translate this {source_label} into {settings.TARGET_LANGUAGE}.

Rules:
- Preserve handles, hashtags, names, URLs, emojis, and line breaks.
- Preserve slang naturally where possible.
- Do not add commentary, notes, labels, or explanations.
- If the text is already in {settings.TARGET_LANGUAGE}, return it unchanged.

Text:
{text}
""".strip()

    response = await client.aio.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0),
    )

    if not response.text:
        raise ValueError("No text response from Gemini")

    return response.text.strip()
