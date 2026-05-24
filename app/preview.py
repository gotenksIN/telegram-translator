from __future__ import annotations

import html
import re
from asyncio import to_thread
from urllib.parse import ParseResult, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from telegram import Message


URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
TRAILING_URL_PUNCTUATION = ".,;!?)]}。．、，；：！？）］｝】」』》〉"
TWITTER_HOSTS = {"twitter.com", "mobile.twitter.com", "x.com", "mobile.x.com"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
PREVIEW_HOST = "hitlerx.com"


class _YtDlpLogger:
    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


def extract_preview_url(message: Message) -> str | None:
    source_url = extract_twitter_status_url(message)
    if source_url is None:
        return None
    return twitter_url_to_preview_url(source_url)


def extract_twitter_status_url(message: Message) -> str | None:
    for text in (message.text, message.caption):
        if not text:
            continue
        for url in extract_urls(text):
            if is_supported_twitter_url(urlparse(url)):
                return url

    return None


def extract_urls(text: str) -> list[str]:
    return [match.group(0).rstrip(TRAILING_URL_PUNCTUATION) for match in URL_RE.finditer(text)]


def extract_first_url(text: str) -> str | None:
    urls = extract_urls(text)
    return urls[0] if urls else None


def is_youtube_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").removeprefix("www.")
    return host in YOUTUBE_HOSTS


def twitter_url_to_preview_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not is_supported_twitter_url(parsed):
        return None
    return urlunparse(("https", PREVIEW_HOST, parsed.path.rstrip("/"), "", "", ""))


def is_supported_twitter_url(parsed_url: ParseResult) -> bool:
    if parsed_url.scheme not in {"http", "https"}:
        return False

    host = (parsed_url.hostname or "").removeprefix("www.")
    if host not in TWITTER_HOSTS:
        return False

    parts = [part for part in parsed_url.path.split("/") if part]
    if len(parts) == 3 and parts[1] == "status" and parts[2].isdigit():
        return True
    if len(parts) == 5 and parts[1] == "status" and parts[2].isdigit() and parts[3] == "photo" and parts[4].isdigit():
        return True
    return len(parts) == 3 and parts[0] == "i" and parts[1] == "status" and parts[2].isdigit()


async def fetch_preview_text(url: str, timeout_seconds: float) -> str:
    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": "TelegramTranslateBot/0.1"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

    text = extract_preview_text(response.text)
    if not text:
        raise ValueError("Could not extract text from preview metadata")

    return text


async def fetch_youtube_preview_text(url: str, timeout_seconds: float, cookies_path: str | None = None) -> str:
    return await to_thread(_extract_youtube_preview_text, url, timeout_seconds, cookies_path)


def _extract_youtube_preview_text(url: str, timeout_seconds: float, cookies_path: str | None) -> str:
    from yt_dlp import YoutubeDL

    options: dict = {
        "check_formats": False,
        "extract_flat": False,
        "extractor_args": {"youtube": {"player_client": ["web"] if cookies_path else ["ios", "android", "web"]}},
        "geo_bypass": True,
        "ignore_no_formats_error": True,
        "ignoreerrors": False,
        "logger": _YtDlpLogger(),
        "no_warnings": True,
        "noplaylist": True,
        "quiet": True,
        "skip_download": True,
        "socket_timeout": timeout_seconds,
    }
    if cookies_path:
        options["cookiefile"] = cookies_path
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not isinstance(info, dict):
        raise ValueError("Could not extract YouTube metadata")

    entries = info.get("entries")
    if isinstance(entries, list):
        info = next((entry for entry in entries if isinstance(entry, dict)), info)

    text = format_youtube_preview_text(info)
    if not text:
        raise ValueError("Could not extract YouTube preview text")
    return text


def format_youtube_preview_text(info: dict) -> str:
    parts: list[str] = []
    title = _clean_metadata_value(info.get("title"))
    description = _clean_metadata_value(info.get("description"))
    channel = _clean_metadata_value(info.get("channel") or info.get("uploader"))

    if title:
        parts.append(title)
    if description and description != title:
        parts.append(description)
    if channel:
        parts.append(f"Channel: {channel}")

    tags = info.get("tags")
    if isinstance(tags, list):
        clean_tags = [_clean_metadata_value(tag) for tag in tags[:30]]
        clean_tags = [tag for tag in clean_tags if tag]
        if clean_tags:
            parts.append("Tags: " + ", ".join(clean_tags))

    return "\n\n".join(parts).strip()


def _clean_metadata_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return _clean_preview_text(value) or None


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
