from __future__ import annotations

import html
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from telegram import Message


URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
TRAILING_URL_PUNCTUATION = ".,;!?)]}。．、，；：！？）］｝】」』》〉"
LINKCLEANER_PREVIEW_HOST = "fixupx.com"


def extract_preview_url(message: Message) -> str | None:
    link_preview_options = message.link_preview_options
    if link_preview_options is not None and link_preview_options.url:
        url = str(link_preview_options.url)
        if is_linkcleaner_preview_url(url):
            return url

    return None


def extract_first_url(text: str) -> str | None:
    match = URL_RE.search(text)
    if match is None:
        return None
    return match.group(0).rstrip(TRAILING_URL_PUNCTUATION)


def is_linkcleaner_preview_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.hostname or ""
    return host == LINKCLEANER_PREVIEW_HOST


async def fetch_preview_text(url: str, timeout_seconds: float) -> str:
    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": "TelegramTwitterTranslateBot/0.1"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

    text = extract_preview_text(response.text)
    if not text:
        raise ValueError("Could not extract text from preview metadata")

    return text


def extract_preview_text(page_html: str) -> str | None:
    soup = BeautifulSoup(page_html, "html.parser")
    for key in ("og:description", "twitter:description", "description"):
        value = _meta_content(soup, key)
        if value:
            return _clean_preview_text(value)

    title = _meta_content(soup, "og:title") or _title_text(soup)
    if title:
        return _clean_preview_text(title)

    return None


def _meta_content(soup: BeautifulSoup, key: str) -> str | None:
    tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
    if tag is None:
        return None
    content = tag.get("content")
    if not isinstance(content, str):
        return None
    return content.strip() or None


def _title_text(soup: BeautifulSoup) -> str | None:
    if soup.title is None or soup.title.string is None:
        return None
    return soup.title.string.strip() or None


def _clean_preview_text(value: str) -> str:
    value = html.unescape(value).replace("\r\n", "\n").replace("\r", "\n")
    value = BR_RE.sub("\n", value)
    lines = [line.strip() for line in value.split("\n")]
    return "\n".join(line for line in lines if line).strip()
