from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
from asyncio import get_running_loop, timeout, to_thread, wait_for
from urllib.parse import ParseResult, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from telegram import Message
from telegram.constants import MessageEntityType

URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
TRAILING_URL_PUNCTUATION = ".,;!?)]}。．、，；：！？）］｝】」』》〉"
TWITTER_HOSTS = {"twitter.com", "mobile.twitter.com", "x.com", "mobile.x.com"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
YOUTUBE_POST_PATH_RE = re.compile(r"^/post/[^/]+/?$")
DEFAULT_TWITTER_PREVIEW_HOST = "girlcockx.com"
MAX_PREVIEW_REDIRECTS = 5
MAX_PREVIEW_BODY_BYTES = 2 * 1024 * 1024


class _YtDlpLogger:
    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


def extract_message_urls(message: Message) -> list[str]:
    urls: list[str] = []

    link_preview_options = getattr(message, "link_preview_options", None)
    if link_preview_options is not None:
        link_url = getattr(link_preview_options, "url", None)
        if link_url:
            urls.append(link_url)

    text_urls = _extract_entity_urls(getattr(message, "parse_entities", None))
    if not text_urls and (text := getattr(message, "text", None)):
        text_urls = extract_urls(text)
    urls.extend(text_urls)

    caption_urls = _extract_entity_urls(getattr(message, "parse_caption_entities", None))
    if not caption_urls and (caption := getattr(message, "caption", None)):
        caption_urls = extract_urls(caption)
    urls.extend(caption_urls)

    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def _extract_entity_urls(parse_fn: object) -> list[str]:
    if not callable(parse_fn):
        return []

    try:
        entities = parse_fn([MessageEntityType.URL, MessageEntityType.TEXT_LINK])
    except TypeError:
        entities = parse_fn()

    if not isinstance(entities, dict):
        return []

    urls: list[str] = []
    for entity, text in entities.items():
        if getattr(entity, "type", None) == MessageEntityType.TEXT_LINK:
            url = getattr(entity, "url", None)
            if url:
                urls.append(url)
        elif getattr(entity, "type", None) == MessageEntityType.URL and text:
            cleaned = text.rstrip(TRAILING_URL_PUNCTUATION)
            if cleaned:
                parsed = urlparse(cleaned)
                if not parsed.scheme or "://" not in cleaned:
                    cleaned = f"https://{cleaned}"
                cleaned = cleaned.rstrip(TRAILING_URL_PUNCTUATION)
                urls.append(cleaned)
    return urls


def extract_preview_url(message: Message, preview_host: str = DEFAULT_TWITTER_PREVIEW_HOST) -> str | None:
    source_url = extract_twitter_status_url(message)
    if source_url is None:
        return None
    return twitter_url_to_preview_url(source_url, preview_host)


def extract_twitter_status_url(message: Message) -> str | None:
    for url in extract_message_urls(message):
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


def twitter_url_to_preview_url(url: str, preview_host: str = DEFAULT_TWITTER_PREVIEW_HOST) -> str | None:
    parsed = urlparse(url)
    if not is_supported_twitter_url(parsed):
        return None
    return urlunparse(("https", preview_host, parsed.path.rstrip("/"), "", "", ""))


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
    page_html = await _fetch_preview_html(url, timeout_seconds, "TelegramTranslateBot/0.1")
    text = extract_preview_text(page_html)
    if not text:
        raise ValueError("Could not extract text from preview metadata")
    return text


async def _fetch_preview_html(url: str, timeout_seconds: float, user_agent: str) -> str:
    async with timeout(timeout_seconds):
        return await _fetch_validated_preview_html(url, timeout_seconds, user_agent)


async def _fetch_validated_preview_html(url: str, timeout_seconds: float, user_agent: str) -> str:
    deadline = get_running_loop().time() + timeout_seconds
    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": user_agent, "Accept-Encoding": "identity"},
    ) as client:
        next_url = url
        for _ in range(MAX_PREVIEW_REDIRECTS + 1):
            addresses = await validate_public_http_url(next_url)
            original_url = httpx.URL(next_url)
            resolved = sorted(addresses, key=str)
            for index, address in enumerate(resolved):
                pinned_url = original_url.copy_with(host=str(address))
                client.cookies.clear()
                connect_timeout = max(0.001, (deadline - get_running_loop().time()) / (len(resolved) - index))
                try:
                    async with client.stream(
                        "GET",
                        pinned_url,
                        headers={"Host": original_url.netloc.decode("ascii")},
                        extensions={"sni_hostname": original_url.raw_host.decode("ascii")},
                        timeout=httpx.Timeout(timeout_seconds, connect=connect_timeout),
                    ) as response:
                        if response.is_redirect and (location := response.headers.get("location")):
                            next_url = urljoin(next_url, location)
                            break
                        response.raise_for_status()
                        if response.headers.get("content-encoding", "identity").lower() != "identity":
                            raise ValueError("Compressed preview responses are not supported")
                        body = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            body.extend(chunk)
                            if len(body) > MAX_PREVIEW_BODY_BYTES:
                                raise ValueError("Preview response exceeds size limit")
                        return body.decode(response.encoding or "utf-8", errors="replace")
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    if index == len(resolved) - 1:
                        raise

    raise ValueError("Too many preview redirects")


async def validate_public_http_url(url: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid preview URL") from exc
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Preview URL must use http or https")

    if not hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("Preview URL must include a hostname")

    try:
        addresses = await to_thread(_resolve_host_addresses, hostname, port)
    except OSError as exc:
        raise ValueError("Could not resolve preview URL host") from exc

    if not addresses:
        raise ValueError("Could not resolve preview URL host")
    if any(not address.is_global or address.is_multicast or address.is_reserved for address in addresses):
        raise ValueError("Preview URL resolves to a non-public address")
    return addresses


def _resolve_host_addresses(hostname: str, port: int | None) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    results = socket.getaddrinfo(hostname, port or 443, type=socket.SOCK_STREAM)
    return {ipaddress.ip_address(result[4][0]) for result in results}


async def fetch_youtube_preview_text(url: str, timeout_seconds: float, cookies_path: str | None = None) -> str:
    if is_youtube_post_url(url):
        return await fetch_youtube_post_text(url, timeout_seconds)
    try:
        return await wait_for(
            to_thread(_extract_youtube_preview_text, url, timeout_seconds, cookies_path), timeout_seconds
        )
    except TypeError as exc:
        raise ValueError(str(exc)) from exc


def is_youtube_post_url(url: str) -> bool:
    parsed = urlparse(url)
    return is_youtube_url(url) and YOUTUBE_POST_PATH_RE.fullmatch(parsed.path) is not None


async def fetch_youtube_post_text(url: str, timeout_seconds: float) -> str:
    page_html = await _fetch_preview_html(url, timeout_seconds, "Mozilla/5.0")
    text = extract_youtube_post_text(page_html)
    if not text:
        raise ValueError("Could not extract YouTube post text")
    return text


def extract_youtube_post_text(page_html: str) -> str | None:
    soup = BeautifulSoup(page_html, "html.parser")
    for script in soup.find_all("script"):
        content = script.string
        if not content or '"discussionForumPosting"' not in content:
            continue
        match = re.search(r'"discussionForumPosting":\s*', content)
        if not match:
            continue
        try:
            post, _ = json.JSONDecoder().raw_decode(content, match.end())
        except (json.JSONDecodeError, TypeError):
            continue
        text = post.get("text") if isinstance(post, dict) else None
        if isinstance(text, str):
            return _clean_preview_text(text) or None
    return None


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
        raise TypeError("Could not extract YouTube metadata")

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
