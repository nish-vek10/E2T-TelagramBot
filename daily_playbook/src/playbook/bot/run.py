# daily_playbook/src/playbook/bot/run.py
from __future__ import annotations

import asyncio
import os

from loguru import logger

from playbook.config import PlaybookConfig
from playbook.utils.log import setup_logger
from playbook.bot.build import build_message
from playbook.bot.scheduler import start_daily_job
from playbook.bot.telegram_client import send_message


def _get_env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return (v or default).strip()


async def run_once(cfg: PlaybookConfig) -> None:
    msg = build_message(cfg)

    logger.info(f"CHAT_ID = {cfg.chat_id}")
    logger.info(f"DRY_RUN = {cfg.dry_run}")

    print("\n" + "=" * 90)
    print("DAILY PLAYBOOK OUTPUT (DRY RUN)" if cfg.dry_run else "DAILY PLAYBOOK OUTPUT (LIVE)")
    print("=" * 90 + "\n")
    print(msg)
    print("\n" + "=" * 90 + "\n")

    send_live = os.getenv("PLAYBOOK_SEND_TELEGRAM", "0").strip().lower() in ("1", "true", "yes", "on")
    bot_token = os.getenv("PLAYBOOK_BOT_TOKEN", "").strip()

    if send_live:
        if not bot_token:
            raise RuntimeError("PLAYBOOK_SEND_TELEGRAM=1 but PLAYBOOK_BOT_TOKEN is empty.")
        send_message(bot_token=bot_token, chat_id=cfg.chat_id, text=msg)
        logger.info("Sent playbook to Telegram.")


def main() -> int:
    setup_logger()
    cfg = PlaybookConfig.load()

    run_once_flag = _get_env("PLAYBOOK_RUN_ONCE", "0").lower() in ("1", "true", "yes", "on")
    logger.info(f"RUN_ONCE env = {_get_env('PLAYBOOK_RUN_ONCE', '0')} -> {run_once_flag}")

    if run_once_flag:
        asyncio.run(run_once(cfg))
        return 0

    async def job():
        await run_once(cfg)

    async def forever():
        logger.info(f"Scheduling Daily Playbook at {cfg.post_time} ({cfg.tz})")
        start_daily_job(tz=cfg.tz, hhmm=cfg.post_time, job_coro=job)
        logger.info("Scheduler started; entering keepalive loop.")
        while True:
            await asyncio.sleep(3600)

    asyncio.run(forever())
    return 0
