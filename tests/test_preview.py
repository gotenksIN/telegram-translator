import ipaddress
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, call
from urllib.parse import urlparse

import httpx
import pytest

import app.preview as preview


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


def test_format_youtube_preview_text_omits_duplicate_and_invalid_values():
    assert preview.format_youtube_preview_text({"title": "same", "description": "same", "channel": 1}) == "same"
    assert preview.format_youtube_preview_text({}) == ""


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


def test_resolve_host_addresses_uses_stream_socket(monkeypatch):
    getaddrinfo = Mock(
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 443, 0, 0)),
        ]
    )
    monkeypatch.setattr(preview.socket, "getaddrinfo", getaddrinfo)
    assert preview._resolve_host_addresses("example.com", None) == {
        ipaddress.ip_address("8.8.8.8"),
        ipaddress.ip_address("2606:4700:4700::1111"),
    }
    getaddrinfo.assert_called_once_with("example.com", 443, type=socket.SOCK_STREAM)


@pytest.mark.asyncio
async def test_validated_response_follows_relative_redirects(monkeypatch):
    validate = AsyncMock()
    monkeypatch.setattr(preview, "validate_public_http_url", validate)
    redirect = httpx.Response(302, headers={"location": "/next"}, request=httpx.Request("GET", "https://one.example/start"))
    final = httpx.Response(200, text="ok", request=httpx.Request("GET", "https://one.example/next"))
    client = SimpleNamespace(get=AsyncMock(side_effect=[redirect, final]))

    assert await preview._get_validated_preview_response(client, "https://one.example/start") is final
    assert validate.await_args_list == [
        call("https://one.example/start"),
        call("https://one.example/next"),
    ]


@pytest.mark.asyncio
async def test_validated_response_stops_after_redirect_limit(monkeypatch):
    monkeypatch.setattr(preview, "validate_public_http_url", AsyncMock())
    response = httpx.Response(302, headers={"location": "/again"}, request=httpx.Request("GET", "https://example.com/start"))
    client = SimpleNamespace(get=AsyncMock(return_value=response))
    with pytest.raises(ValueError, match="Too many preview redirects"):
        await preview._get_validated_preview_response(client, "https://example.com/start")


@pytest.mark.asyncio
async def test_fetch_preview_text_extracts_response_metadata(monkeypatch):
    response = httpx.Response(
        200,
        text='<meta property="og:description" content="Preview">',
        request=httpx.Request("GET", "https://example.com"),
    )
    monkeypatch.setattr(preview, "_get_validated_preview_response", AsyncMock(return_value=response))
    assert await preview.fetch_preview_text("https://example.com", 3) == "Preview"


@pytest.mark.asyncio
async def test_fetch_preview_text_rejects_missing_metadata(monkeypatch):
    response = httpx.Response(200, text="<html></html>", request=httpx.Request("GET", "https://example.com"))
    monkeypatch.setattr(preview, "_get_validated_preview_response", AsyncMock(return_value=response))
    with pytest.raises(ValueError, match="Could not extract text"):
        await preview.fetch_preview_text("https://example.com", 3)


@pytest.mark.asyncio
async def test_fetch_youtube_preview_text_uses_post_page(monkeypatch):
    fetch_post = AsyncMock(return_value="complete post")
    monkeypatch.setattr(preview, "fetch_youtube_post_text", fetch_post)
    assert await preview.fetch_youtube_preview_text("https://youtube.com/post/Ugkx123", 3, "cookies.txt") == "complete post"
    fetch_post.assert_awaited_once_with("https://youtube.com/post/Ugkx123", 3)


def test_extract_youtube_preview_text_uses_first_playlist_entry(monkeypatch):
    youtube_dl = MagicMock()
    youtube_dl.return_value.__enter__.return_value.extract_info.return_value = {
        "entries": [None, {"title": "Video", "channel": "Channel"}]
    }
    monkeypatch.setattr("yt_dlp.YoutubeDL", youtube_dl)
    assert preview._extract_youtube_preview_text("https://youtu.be/1", 5, "cookies.txt") == "Video\n\nChannel: Channel"
    options = youtube_dl.call_args.args[0]
    assert options["cookiefile"] == "cookies.txt"
    assert options["extractor_args"]["youtube"]["player_client"] == ["web"]


@pytest.mark.parametrize("info", [None, {}, {"entries": [None]}])
def test_extract_youtube_preview_text_rejects_unusable_metadata(monkeypatch, info):
    youtube_dl = MagicMock()
    youtube_dl.return_value.__enter__.return_value.extract_info.return_value = info
    monkeypatch.setattr("yt_dlp.YoutubeDL", youtube_dl)
    with pytest.raises(ValueError, match="Could not extract YouTube"):
        preview._extract_youtube_preview_text("https://youtu.be/1", 5, None)
