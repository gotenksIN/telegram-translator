from app.main import TELEGRAM_MESSAGE_LIMIT, split_telegram_message


def test_split_telegram_message_skips_empty_chunks() -> None:
    text = "\n" * (TELEGRAM_MESSAGE_LIMIT + 10)

    assert split_telegram_message(text) == []


def test_split_telegram_message_preserves_non_empty_chunks() -> None:
    text = "hello" + "\n" * TELEGRAM_MESSAGE_LIMIT + "world"

    assert split_telegram_message(text) == ["hello", "world"]
