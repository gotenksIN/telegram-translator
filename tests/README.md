# Test contracts

The test suite is organized around the production module boundaries in `app/`.
Each test file imports behavior directly from its owning module.

## Test layout

| Path | Intended owner | Scope |
| --- | --- | --- |
| `tests/test_settings.py` | `app/settings.py` | Environment variable validation, default values, type parsing, URL checks, and invalid configuration rejection. |
| `tests/test_preview.py` | `app/preview.py` | URL extraction, Twitter URL rewriting, SSRF IP validation, redirect loop protection, YouTube post scraping, `yt-dlp` metadata extraction, and HTML preview parsing. |
| `tests/test_gemini.py` | `app/gemini.py` | Gemini client configuration, prompt synthesis across source types, structured `TranslationResponse` validation, thinking configuration, and API timeouts. |
| `tests/test_main.py` | `app/main.py` | Telegram command handling, reply checks, concurrency semaphore enforcement, sliding window rate limits, typing indicators, error replies, message chunking, and link preview attachment. |
| `tests/conftest.py` | Test infrastructure | Pytest configuration, asyncio event loop setups, and shared test fixtures. |

## Automated contracts

| Area | Observable contract |
| --- | --- |
| Settings | Required environment presence, default fallback values, thinking level enum validation, URL scheme and netloc validation, positive float timeouts, and hostname isolation. |
| Preview | Regex URL matching, trailing punctuation stripping, Twitter host detection and rewrite paths, DNS resolution, non-public IP rejection (loopback, private, link-local, multicast), redirect limits, YouTube community post JSON extraction, `yt-dlp` field mapping, OpenGraph and meta tag fallback hierarchy, and HTML whitespace cleaning. |
| Gemini | Structured response deserialization, missing response handling, prompt rule preservation across message, tweet, and preview types, thinking level configuration, and timeout enforcement. |
| Main | Command routing for `/translate_preview` and `/translate_message`, self-reply rejection, missing URL rejection, concurrency exhaustion replies, sliding window rate throttling and retry-after calculation, message splitting at newline boundaries within 4096 characters, and link preview attachment to first chunks only. |

Tests assert returned values, exceptions, message text, and outbound payloads.
Tests do not assert private helper calls or internal execution order unless ordering changes an observable contract.

## Test boundaries

Settings tests use monkeypatching to isolate environment variables.

Preview tests mock `socket.getaddrinfo` and HTTPX network calls to verify SSRF and scraping behaviors without live internet access.
`yt-dlp` tests verify metadata mapping through simulated extraction dictionaries.

Gemini tests mock Google GenAI client methods and verify payload configs and structured responses without issuing billable API calls.

Main bot tests use asynchronous mocks for Telegram `Update`, `Message`, and `Context` objects to verify bot logic in isolation from the Telegram Bot API network.

## Review-only specifications

The following details remain specified in `AGENTS.md` and `CONTEXT.md` but are not frozen by automated tests:

- Exact prompt prose, system wording, and instruction ordering.
- Private helper function names and module-internal variable names.
- Exact user-agent string formats.
- Internal test mock topologies and patch paths.
- Exact threading mechanism used for blocking operations.

Review these details against `AGENTS.md` and `CONTEXT.md` when their implementation changes.
Do not add source-text, prompt snapshot, private-call, or helper-name assertions.

## Commands

Run the complete suite:

```bash
uv run pytest
```

Run one specific module test file:

```bash
uv run pytest tests/test_settings.py
uv run pytest tests/test_preview.py
uv run pytest tests/test_gemini.py
uv run pytest tests/test_main.py
```
