# twitter-translate-bot

Telegram bot that translates a LinkCleaner Twitter/X preview using Gemini.

## Usage

Reply to a LinkCleaner Twitter/X preview message:

```text
/translate@BotUserName
```

The bot reads the replied message's Telegram link preview URL, fetches that preview page, and replies with the translation:

```text
Translation:
...
```

Translations are globally limited to 3 running requests at a time and 10 accepted requests per minute.
Only `fixupx.com` URLs from Telegram link preview metadata are fetched. LinkCleaner currently exposes the original Twitter/X URL in message text and the TweetFix preview URL through Telegram's link preview metadata; this bot intentionally uses the preview URL only.

## Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Set at least:

```env
TELEGRAM_BOT_TOKEN=
GEMINI_API_KEY=
```

Optional Gemini proxy support matches the existing `GEMINI_API_BASE` convention:

```env
GEMINI_API_BASE=https://your-proxy.example/gemini
GEMINI_MODEL=gemini-3.1-pro-preview
```

Optional preview/translation settings:

```env
TARGET_LANGUAGE=English
REQUEST_TIMEOUT_SECONDS=10
```

## Run

Install dependencies with `uv`:

```bash
uv sync
```

Start the bot:

```bash
uv run python -m app.main
```
