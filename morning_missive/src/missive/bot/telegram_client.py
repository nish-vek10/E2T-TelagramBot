# morning_missive/src/missive/bot/telegram_client.py

from __future__ import annotations

import asyncio
from telegram import Bot

from missive.utils.text import chunk_telegram


async def _send_async(bot_token: str, chat_id: str, text: str) -> None:
    bot = Bot(token=bot_token)
    for part in chunk_telegram(text):
        await bot.send_message(
            chat_id=chat_id,
            text=part,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

def send_message(bot_token: str, chat_id: str, text: str) -> None:
    asyncio.run(_send_async(bot_token, chat_id, text))
