# telegram-translate-bot

Telegram bot that translates messages and LinkCleaner Twitter/X previews using Gemini.

## Usage

The bot provides two commands:

**`/translate_preview`** — Translate a replied LinkCleaner Twitter/X preview:

```text
/translate_preview@BotUserName
```

The bot extracts the Twitter/X status URL from the replied message, rewrites it to `hitlerx.com`, fetches that preview page, and replies with the translation.

**`/translate_message`** — Translate the text of any replied message directly:

```text
/translate_message@BotUserName
```

The bot takes the replied message's text/caption directly and translates it with Gemini. No URL extraction or preview fetching is involved.

The bot registers both commands in Telegram's command menu for private chats and groups.

Example reply format:

```text
Translation:
...
```

Translations are globally limited to 3 running requests at a time and 10 accepted requests per minute.
For `/translate_preview`, only Twitter/X status URLs from the replied message text are accepted. Telegram link preview metadata is intentionally ignored because FixupX can sometimes return already-translated content.

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

## User systemd service

A user-mode systemd unit is available at `systemd/telegram-translator.service`. It assumes the repo is cloned to `~/telegram-translator` on the target machine.

```bash
uv sync --frozen
mkdir -p ~/.config/systemd/user
cp systemd/telegram-translator.service ~/.config/systemd/user/telegram-translator.service
systemctl --user daemon-reload
systemctl --user enable --now telegram-translator.service
```

To run after login sessions end, enable lingering on the target machine:

```bash
loginctl enable-linger "$USER"
```
