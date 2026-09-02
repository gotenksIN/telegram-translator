import ipaddress
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from urllib.parse import urlparse

import httpx
import pytest
from telegram import Message, MessageEntity
from telegram.constants import MessageEntityType

from app import preview


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("See https://example.com/a, then http://example.org/b).", ["https://example.com/a", "http://example.org/b"]),
        ("nothing here", []),
    ],
)
def test_extract_urls(text, expected):
    assert preview.extract_urls(text) == expected
    assert preview.extract_first_url(text) == (expected[0] if expected else None)


@pytest.mark.parametrize(
    "url",
    [
        "https://twitter.com/user/status/123",
        "http://www.x.com/user/status/123?ref=x",
        "https://mobile.twitter.com/user/status/123/photo/2",
        "https://x.com/i/status/123",
    ],
)
def test_supported_twitter_urls_are_rewritten(url):
    assert preview.twitter_url_to_preview_url(url, "preview.example") == (
        "https://preview.example" + urlparse(url).path.rstrip("/")
    )


@pytest.mark.parametrize(
    "url",
    [
        "ftp://x.com/user/status/123",
        "https://example.com/user/status/123",
        "https://x.com/user/status/not-a-number",
        "https://x.com/user/status/123/video/1",
    ],
)
def test_unsupported_twitter_urls_are_rejected(url):
    assert preview.twitter_url_to_preview_url(url) is None


def test_extracts_twitter_url_from_text_then_caption():
    message = SimpleNamespace(
        text="unrelated https://example.com then https://x.com/user/status/123",
        caption="https://twitter.com/other/status/456",
    )
    assert preview.extract_twitter_status_url(message) == "https://x.com/user/status/123"
    assert preview.extract_preview_url(message, "preview.example") == "https://preview.example/user/status/123"


def test_extract_message_urls_from_text_link_entities():
    entity = MessageEntity(type=MessageEntityType.TEXT_LINK, offset=0, length=4, url="https://example.com/inline")
    message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=None,
        text="link",
        entities=[entity],
    )
    assert preview.extract_message_urls(message) == ["https://example.com/inline"]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://youtube.com/watch?v=1", True),
        ("https://www.youtube.com/watch?v=1", True),
        ("http://youtu.be/1", True),
        ("ftp://youtube.com/video", False),
        ("https://notyoutube.com/video", False),
    ],
)
def test_is_youtube_url(url, expected):
    assert preview.is_youtube_url(url) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://youtube.com/post/Ugkx123", True),
        ("https://www.youtube.com/post/Ugkx123/", True),
        ("https://youtube.com/watch?v=1", False),
        ("https://example.com/post/Ugkx123", False),
    ],
)
def test_is_youtube_post_url(url, expected):
    assert preview.is_youtube_post_url(url) is expected


def test_extract_youtube_post_text_uses_structured_full_text():
    page_html = """
    <script>
    var data = {"postDetails":{"discussionForumPosting":{"type":"DiscussionForumPosting",
    "text":"Full &amp; untruncated\\npost","image":["image"]}}}};
    </script>
    """
    assert preview.extract_youtube_post_text(page_html) == "Full & untruncated\npost"


def test_extract_youtube_post_text_rejects_missing_or_malformed_data():
    assert preview.extract_youtube_post_text("<script>{}</script>") is None
    assert preview.extract_youtube_post_text('<script>{"discussionForumPosting": nope}}};</script>') is None


@pytest.mark.parametrize(
    ("page_html", "expected"),
    [
        ('<meta property="og:description" content=" A &amp; B &lt;br&gt; C ">', "A & B\nC"),
        ('<meta name="twitter:description" content="Twitter text">', "Twitter text"),
        ('<meta name="description" content="Description">', "Description"),
        ('<meta property="og:title" content="Open Graph title">', "Open Graph title"),
        ("<title> Page title </title>", "Page title"),
        ("<html></html>", None),
    ],
)
def test_extract_preview_text_uses_metadata_priority(page_html, expected):
    assert preview.extract_preview_text(page_html) == expected


def test_format_youtube_preview_text_cleans_and_limits_metadata():
    info = {
        "title": " Title ",
        "description": "Line 1<br>Line 2",
        "uploader": " Creator ",
        "tags": [f" tag {index} " for index in range(35)] + [None],
    }
    text = preview.format_youtube_preview_text(info)
    assert text.startswith("Title\n\nLine 1\nLine 2\n\nChannel: Creator\n\nTags: tag 0")
    assert "tag 29" in text
    assert "tag 30" not in text


@pytest.mark.asyncio
async def test_validate_public_http_url_accepts_only_global_addresses(monkeypatch):
    monkeypatch.setattr(
        preview,
        "_resolve_host_addresses",
        Mock(return_value={ipaddress.ip_address("8.8.8.8"), ipaddress.ip_address("2606:4700:4700::1111")}),
    )
    await preview.validate_public_http_url("https://example.com/path")


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["ftp://example.com", "https:///path"])
async def test_validate_public_http_url_rejects_malformed_urls(url):
    with pytest.raises(ValueError, match="must use http|include a hostname"):
        await preview.validate_public_http_url(url)


@pytest.mark.asyncio
async def test_validate_public_http_url_rejects_resolution_failures_and_private_addresses(monkeypatch):
    monkeypatch.setattr(preview, "_resolve_host_addresses", Mock(side_effect=OSError))
    with pytest.raises(ValueError, match="Could not resolve"):
        await preview.validate_public_http_url("https://example.com")

    monkeypatch.setattr(preview, "_resolve_host_addresses", Mock(return_value=set()))
    with pytest.raises(ValueError, match="Could not resolve"):
        await preview.validate_public_http_url("https://example.com")

    monkeypatch.setattr(preview, "_resolve_host_addresses", Mock(return_value={ipaddress.ip_address("127.0.0.1")}))
    with pytest.raises(ValueError, match="non-public"):
        await preview.validate_public_http_url("https://example.com")


def mock_http_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        preview,
        "_resolve_host_addresses",
        Mock(return_value={ipaddress.ip_address("8.8.8.8")}),
    )
    monkeypatch.setattr(
        preview.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )


@pytest.mark.asyncio
async def test_fetch_preview_text_follows_relative_redirects(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/next"})
        if request.url.path == "/next":
            return httpx.Response(200, text='<meta property="og:description" content="ok">')
        return httpx.Response(404)

    mock_http_transport(monkeypatch, handler)
    assert await preview.fetch_preview_text("https://one.example/start", 3) == "ok"


@pytest.mark.asyncio
async def test_fetch_preview_text_stops_after_redirect_limit(monkeypatch):
    mock_http_transport(monkeypatch, lambda req: httpx.Response(302, headers={"location": "/again"}))
    with pytest.raises(ValueError, match="Too many preview redirects"):
        await preview.fetch_preview_text("https://example.com/start", 3)


@pytest.mark.asyncio
async def test_fetch_preview_text_extracts_response_metadata(monkeypatch):
    mock_http_transport(
        monkeypatch,
        lambda req: httpx.Response(200, text='<meta property="og:description" content="Preview">'),
    )
    assert await preview.fetch_preview_text("https://example.com", 3) == "Preview"


@pytest.mark.asyncio
async def test_fetch_preview_text_rejects_missing_metadata(monkeypatch):
    mock_http_transport(monkeypatch, lambda req: httpx.Response(200, text="<html></html>"))
    with pytest.raises(ValueError, match="Could not extract text"):
        await preview.fetch_preview_text("https://example.com", 3)


@pytest.mark.asyncio
async def test_fetch_youtube_preview_text_extracts_community_post(monkeypatch):
    post_html = '<script>{"postDetails":{"discussionForumPosting":{"text":"complete post"}}}</script>'
    mock_http_transport(monkeypatch, lambda req: httpx.Response(200, text=post_html))
    assert (
        await preview.fetch_youtube_preview_text("https://youtube.com/post/Ugkx123", 3, "cookies.txt")
        == "complete post"
    )


@pytest.mark.asyncio
async def test_extract_youtube_preview_text_uses_first_playlist_entry(monkeypatch):
    youtube_dl = MagicMock()
    youtube_dl.return_value.__enter__.return_value.extract_info.return_value = {
        "entries": [None, {"title": "Video", "channel": "Channel"}]
    }
    monkeypatch.setattr("yt_dlp.YoutubeDL", youtube_dl)
    assert (
        await preview.fetch_youtube_preview_text("https://youtu.be/1", 5, "cookies.txt") == "Video\n\nChannel: Channel"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("info", [None, {}, {"entries": [None]}])
async def test_extract_youtube_preview_text_rejects_unusable_metadata(monkeypatch, info):
    youtube_dl = MagicMock()
    youtube_dl.return_value.__enter__.return_value.extract_info.return_value = info
    monkeypatch.setattr("yt_dlp.YoutubeDL", youtube_dl)
    with pytest.raises(ValueError, match="Could not extract YouTube"):
        await preview.fetch_youtube_preview_text("https://youtu.be/1", 5, None)
