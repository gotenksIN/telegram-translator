from asyncio import BoundedSemaphore
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from telegram.constants import ChatAction

from app import main


def install_limits(context, timestamps=()):
    context.application.bot_data[main.TRANSLATION_SEMAPHORE_KEY] = BoundedSemaphore(main.MAX_RUNNING_TRANSLATIONS)
    context.application.bot_data[main.TRANSLATION_TIMESTAMPS_KEY] = deque(timestamps)


def replied_message(text=None, caption=None, user_id=1):
    return SimpleNamespace(text=text, caption=caption, from_user=SimpleNamespace(id=user_id))


def test_split_telegram_message_handles_empty_short_newline_and_hard_splits(monkeypatch):
    monkeypatch.setattr(main, "TELEGRAM_MESSAGE_LIMIT", 10)
    assert main.split_telegram_message("   ") == []
    assert main.split_telegram_message(" short ") == ["short"]
    assert main.split_telegram_message("first\nsecond") == ["first", "second"]
    assert main.split_telegram_message("abcdefghijkl") == ["abcdefghij", "kl"]


@pytest.mark.asyncio
async def test_reply_long_text_sends_chunks_and_preview_only_on_first(monkeypatch):
    monkeypatch.setattr(main, "TELEGRAM_MESSAGE_LIMIT", 5)
    message = SimpleNamespace(reply_text=AsyncMock())
    await main.reply_long_text(message, "12345\n67890", preview_url="https://example.com")
    assert message.reply_text.await_count == 2
    first, second = message.reply_text.await_args_list
    assert first.args == ("12345",)
    assert first.kwargs["do_quote"] is True
    assert first.kwargs["link_preview_options"].url == "https://example.com"
    assert second == call("67890", do_quote=True, link_preview_options=None)


@pytest.mark.asyncio
async def test_reply_long_text_supplies_fallback_for_empty_text():
    message = SimpleNamespace(reply_text=AsyncMock())
    await main.reply_long_text(message, "")
    message.reply_text.assert_awaited_once_with("No text to send.", do_quote=True, link_preview_options=None)


def test_reserve_translation_rate_slot_prunes_accepts_and_limits(monkeypatch):
    monkeypatch.setattr(main, "MAX_TRANSLATIONS_PER_MINUTE", 2)
    bot_data = {main.TRANSLATION_TIMESTAMPS_KEY: deque([0.0, 59.5])}
    assert main.reserve_translation_rate_slot(bot_data, 60.0) is None
    assert list(bot_data[main.TRANSLATION_TIMESTAMPS_KEY]) == [59.5, 60.0]
    assert main.reserve_translation_rate_slot(bot_data, 60.1) == 60


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reply", "expected", "quoted"),
    [
        (None, "Please reply to a message to translate its text", False),
        (replied_message("text", user_id=999), "The message has already been translated", True),
        (replied_message(), "The replied message has no text to translate.", False),
    ],
)
async def test_translate_message_validates_reply(command_objects, reply, expected, quoted):
    update, context, message, _ = command_objects
    message.reply_to_message = reply
    await main.translate_message_command(update, context)
    kwargs = {"do_quote": True} if quoted else {}
    message.reply_text.assert_awaited_once_with(expected, **kwargs)


@pytest.mark.asyncio
async def test_translate_message_translates_caption(command_objects, monkeypatch):
    update, context, message, bot = command_objects
    message.reply_to_message = replied_message(caption="hola")
    install_limits(context)
    translate = AsyncMock(return_value={"translated_text": "hello", "source_language": "Spanish"})
    reply_long = AsyncMock()
    monkeypatch.setattr(main, "translate_text", translate)
    monkeypatch.setattr(main, "reply_long_text", reply_long)

    await main.translate_message_command(update, context)

    bot.send_chat_action.assert_awaited_once_with(chat_id=123, action=ChatAction.TYPING)
    translate.assert_awaited_once_with("hola", context.application.bot_data["settings"], source_type="message")
    reply_long.assert_awaited_once_with(message, "Translation from Spanish:\n\nhello")


@pytest.mark.asyncio
async def test_translate_message_handles_translation_failure(command_objects, monkeypatch):
    update, context, message, _ = command_objects
    message.reply_to_message = replied_message(text="hola")
    install_limits(context)
    monkeypatch.setattr(main, "translate_text", AsyncMock(side_effect=RuntimeError))
    reply_long = AsyncMock()
    monkeypatch.setattr(main, "reply_long_text", reply_long)
    await main.translate_message_command(update, context)
    reply_long.assert_awaited_once_with(message, "Could not translate this message.")


@pytest.mark.asyncio
async def test_translate_message_rejects_busy_and_rate_limited_requests(command_objects, monkeypatch):
    update, context, message, _ = command_objects
    message.reply_to_message = replied_message(text="hola")
    semaphore = Mock(locked=Mock(return_value=True))
    context.application.bot_data[main.TRANSLATION_SEMAPHORE_KEY] = semaphore
    await main.translate_message_command(update, context)
    message.reply_text.assert_awaited_once_with(
        "Too many translations are running. Please try again shortly.", do_quote=True
    )

    message.reply_text.reset_mock()
    semaphore.locked.return_value = False
    context.application.bot_data[main.TRANSLATION_TIMESTAMPS_KEY] = deque([0] * main.MAX_TRANSLATIONS_PER_MINUTE)
    monkeypatch.setattr(main.time, "monotonic", Mock(return_value=1))
    await main.translate_message_command(update, context)
    message.reply_text.assert_awaited_once_with(
        "Translation rate limit reached. Please try again in 60 seconds.", do_quote=True
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reply", "expected", "quoted"),
    [
        (None, "Please reply to a message containing a URL to translate its preview", False),
        (replied_message("https://example.com", user_id=999), "The message has already been translated", True),
        (replied_message(text="no links"), "Could not find a URL in the replied message.", False),
    ],
)
async def test_translate_preview_validates_reply(command_objects, reply, expected, quoted):
    update, context, message, _ = command_objects
    message.reply_to_message = reply
    await main.translate_preview_command(update, context)
    kwargs = {"do_quote": True} if quoted else {}
    message.reply_text.assert_awaited_once_with(expected, **kwargs)


@pytest.mark.asyncio
async def test_translate_preview_fetches_twitter_preview_and_translates(command_objects, monkeypatch):
    update, context, message, _ = command_objects
    message.reply_to_message = replied_message(text="https://x.com/user/status/123")
    install_limits(context)
    monkeypatch.setattr(main, "fetch_preview_text", AsyncMock(return_value="tweet text"))
    translate = AsyncMock(return_value={"translated_text": "translation", "source_language": "Japanese"})
    monkeypatch.setattr(main, "translate_text", translate)
    reply_long = AsyncMock()
    monkeypatch.setattr(main, "reply_long_text", reply_long)

    await main.translate_preview_command(update, context)

    main.fetch_preview_text.assert_awaited_once_with("https://preview.example/user/status/123", 10.0)
    translate.assert_awaited_once_with("tweet text", context.application.bot_data["settings"], source_type="tweet")
    reply_long.assert_awaited_once_with(
        message,
        "Translation from Japanese for https://x.com/user/status/123:\n\ntranslation",
        preview_url="https://preview.example/user/status/123",
    )


@pytest.mark.asyncio
async def test_translate_preview_uses_generic_url(command_objects, monkeypatch):
    update, context, message, _ = command_objects
    message.reply_to_message = replied_message(text="read https://example.com/page")
    install_limits(context)
    monkeypatch.setattr(main, "fetch_preview_text", AsyncMock(return_value="page text"))
    translate = AsyncMock(return_value={"translated_text": "translation", "source_language": "French"})
    monkeypatch.setattr(main, "translate_text", translate)
    monkeypatch.setattr(main, "reply_long_text", AsyncMock())
    await main.translate_preview_command(update, context)
    translate.assert_awaited_once_with("page text", context.application.bot_data["settings"], source_type="preview")


@pytest.mark.asyncio
async def test_translate_preview_uses_youtube_metadata_then_generic_fallback(command_objects, monkeypatch):
    update, context, message, _ = command_objects
    message.reply_to_message = replied_message(text="https://youtu.be/video")
    install_limits(context)
    youtube = AsyncMock(side_effect=RuntimeError)
    generic = AsyncMock(return_value="fallback")
    monkeypatch.setattr(main, "fetch_youtube_preview_text", youtube)
    monkeypatch.setattr(main, "fetch_preview_text", generic)
    monkeypatch.setattr(
        main, "translate_text", AsyncMock(return_value={"translated_text": "ok", "source_language": "English"})
    )
    monkeypatch.setattr(main, "reply_long_text", AsyncMock())
    await main.translate_preview_command(update, context)
    youtube.assert_awaited_once_with("https://youtu.be/video", 10.0, None)
    generic.assert_awaited_once_with("https://youtu.be/video", 10.0)


@pytest.mark.asyncio
async def test_translate_preview_reports_fetch_failure(command_objects, monkeypatch):
    update, context, message, _ = command_objects
    message.reply_to_message = replied_message(text="https://example.com")
    install_limits(context)
    monkeypatch.setattr(main, "fetch_preview_text", AsyncMock(side_effect=RuntimeError))
    reply_long = AsyncMock()
    monkeypatch.setattr(main, "reply_long_text", reply_long)
    await main.translate_preview_command(update, context)
    reply_long.assert_awaited_once_with(message, "Could not fetch text from the replied preview message.")


@pytest.mark.asyncio
async def test_translate_preview_reports_translation_failure(command_objects, monkeypatch):
    update, context, message, _ = command_objects
    message.reply_to_message = replied_message(text="https://example.com")
    install_limits(context)
    monkeypatch.setattr(main, "fetch_preview_text", AsyncMock(return_value="page"))
    monkeypatch.setattr(main, "translate_text", AsyncMock(side_effect=RuntimeError))
    reply_long = AsyncMock()
    monkeypatch.setattr(main, "reply_long_text", reply_long)
    await main.translate_preview_command(update, context)
    reply_long.assert_awaited_once_with(message, "Could not translate this preview.")
