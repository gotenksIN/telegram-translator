from __future__ import annotations

import logging
import time
from asyncio import BoundedSemaphore
from collections import deque

from telegram import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeDefault,
    LinkPreviewOptions,
    Message,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes

from app.gemini import translate_tweet
from app.preview import extract_preview_url, extract_twitter_status_url, fetch_preview_text
from app.settings import get_settings


logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096
MAX_CONCURRENT_UPDATES = 16
MAX_RUNNING_TRANSLATIONS = 3
MAX_TRANSLATIONS_PER_MINUTE = 10
TRANSLATION_RATE_WINDOW_SECONDS = 60
TRANSLATION_SEMAPHORE_KEY = "translation_semaphore"
TRANSLATION_TIMESTAMPS_KEY = "translation_timestamps"
BOT_COMMANDS = [BotCommand("translate", "Translate a replied LinkCleaner Twitter preview")]


async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None or update.effective_chat is None:
        return

    message = update.effective_message
    chat = update.effective_chat
    settings = context.application.bot_data["settings"]

    replied_message = message.reply_to_message
    if replied_message is None:
        await message.reply_text("Please reply to a message containing Twitter URL")
        return

    preview_url = extract_preview_url(replied_message)
    if preview_url is None:
        await message.reply_text("Could not find a Twitter/X status URL in the replied message.")
        return
    source_url = extract_twitter_status_url(replied_message)

    now = time.monotonic()
    semaphore = context.application.bot_data[TRANSLATION_SEMAPHORE_KEY]
    if semaphore.locked():
        await message.reply_text("Too many translations are running. Please try again shortly.", do_quote=True)
        return

    retry_after = reserve_translation_rate_slot(context.application.bot_data, now)
    if retry_after is not None:
        await message.reply_text(
            f"Translation rate limit reached. Please try again in {retry_after} seconds.", do_quote=True
        )
        return

    await semaphore.acquire()
    try:
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)

        try:
            preview_text = await fetch_preview_text(preview_url, settings.REQUEST_TIMEOUT_SECONDS)
        except Exception:
            logger.exception("Failed to fetch preview text")
            await reply_long_text(message, "Could not fetch text from the replied preview message.")
            return

        try:
            translation = await translate_tweet(preview_text, settings)
        except Exception:
            logger.exception("Failed to translate tweet")
            await reply_long_text(message, "Could not translate this tweet.")
            return
    finally:
        semaphore.release()

    source_line = f"Translation for {source_url}:" if source_url else "Translation for replied Twitter/X status:"
    await reply_long_text(message, f"{source_line}\n\n{translation}", preview_url=preview_url)


async def configure_bot_commands(application: Application) -> None:
    await application.bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())
    await application.bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    await application.bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeAllGroupChats())


def reserve_translation_rate_slot(bot_data: dict, now: float) -> int | None:
    timestamps = bot_data[TRANSLATION_TIMESTAMPS_KEY]
    while timestamps and now - timestamps[0] >= TRANSLATION_RATE_WINDOW_SECONDS:
        timestamps.popleft()

    if len(timestamps) >= MAX_TRANSLATIONS_PER_MINUTE:
        return max(1, int(TRANSLATION_RATE_WINDOW_SECONDS - (now - timestamps[0])) + 1)

    timestamps.append(now)
    return None


async def reply_long_text(message: Message, text: str, preview_url: str | None = None) -> None:
    for index, chunk in enumerate(split_telegram_message(text)):
        link_preview_options = None
        if index == 0 and preview_url is not None:
            link_preview_options = LinkPreviewOptions(url=preview_url, prefer_large_media=True, show_above_text=False)
        await message.reply_text(chunk, do_quote=True, link_preview_options=link_preview_options)


def split_telegram_message(text: str) -> list[str]:
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > TELEGRAM_MESSAGE_LIMIT:
        split_at = remaining.rfind("\n", 0, TELEGRAM_MESSAGE_LIMIT + 1)
        if split_at <= 0:
            split_at = TELEGRAM_MESSAGE_LIMIT
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


def main() -> None:
    settings = get_settings()
    application = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .concurrent_updates(MAX_CONCURRENT_UPDATES)
        .post_init(configure_bot_commands)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data[TRANSLATION_SEMAPHORE_KEY] = BoundedSemaphore(MAX_RUNNING_TRANSLATIONS)
    application.bot_data[TRANSLATION_TIMESTAMPS_KEY] = deque()
    application.add_handler(CommandHandler("translate", translate_command))
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
