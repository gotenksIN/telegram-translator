import asyncio
from ipaddress import ip_address
from types import SimpleNamespace

import pytest

from app import preview


def test_twitter_preview_host_is_configurable() -> None:
    message = SimpleNamespace(text="https://x.com/user/status/123", caption=None)

    assert preview.extract_preview_url(message, "preview.example") == "https://preview.example/user/status/123"


def test_validate_public_http_url_rejects_private_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preview, "_resolve_host_addresses", lambda hostname, port: {ip_address("127.0.0.1")})

    with pytest.raises(ValueError, match="non-public"):
        asyncio.run(preview.validate_public_http_url("https://example.com/path"))


def test_validate_public_http_url_allows_public_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preview, "_resolve_host_addresses", lambda hostname, port: {ip_address("8.8.8.8")})

    asyncio.run(preview.validate_public_http_url("https://example.com/path"))


def test_validate_public_http_url_rejects_non_http_scheme() -> None:
    with pytest.raises(ValueError, match="http or https"):
        asyncio.run(preview.validate_public_http_url("file:///etc/passwd"))
