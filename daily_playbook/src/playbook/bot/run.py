# daily_playbook/src/playbook/bot/run.py
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger

from playbook.config import PlaybookConfig
from playbook.utils.log import setup_logger
from playbook.bot.build import build_message
from playbook.bot.build import build_message_and_raw
from playbook.storage.supabase_client import get_supabase
from playbook.storage.save_playbook import save_playbook_to_supabase
from playbook.bot.telegram_client import send_message


def _get_env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return (v or default).strip()


def _seconds_until_next(hhmm: str, tz: str) -> int:
    tzinfo = ZoneInfo(tz)
    now = datetime.now(tzinfo)

    hh, mm = hhmm.split(":")
    target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)

    if target <= now:
        target = target + timedelta(days=1)

    return max(1, int((target - now).total_seconds()))


async def run_once(cfg: PlaybookConfig) -> None:
    msg, raw = build_message_and_raw(cfg)

    logger.info(f"CHAT_ID = {cfg.chat_id}")
    logger.info(f"DRY_RUN = {cfg.dry_run}")
    logger.info("Playbook message built successfully.")

    # ---- Supabase save (opt-in) ----
    save_enabled = _get_env("PLAYBOOK_SAVE_SUPABASE", "0").lower() in ("1", "true", "yes", "on")
    save_on_dry = _get_env("PLAYBOOK_SAVE_ON_DRY_RUN", "0").lower() in ("1", "true", "yes", "on")
    save_only = _get_env("PLAYBOOK_SAVE_ONLY", "0").lower() in ("1", "true", "yes", "on")

    should_save = save_enabled and (save_on_dry or (not cfg.dry_run))
    if should_save:
        supabase = get_supabase()
        playbook_id = save_playbook_to_supabase(
            supabase=supabase,
            tz=cfg.tz,
            post_time=cfg.post_time,
            telegram_chat_id=cfg.chat_id,
            rendered_text=msg,
            raw_text=raw,
            posted_to_telegram=(not cfg.dry_run and not save_only),
        )
        logger.info(f"[OK] Supabase saved playbook_id={playbook_id}")

    # ---- Telegram send ----
    send_live = _get_env("PLAYBOOK_SEND_TELEGRAM", "0").lower() in ("1", "true", "yes", "on")
    bot_token = _get_env("PLAYBOOK_BOT_TOKEN", "")

    # Save-only test mode: never send TG
    if save_only:
        logger.info("[OK] PLAYBOOK_SAVE_ONLY=1 → Skipping Telegram send.")
        return

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

    async def forever():
        logger.info(f"[OK] Scheduling Daily Playbook at {cfg.post_time} ({cfg.tz})")
        logger.info("[OK] Keepalive loop started (Heroku-safe).")

        while True:
            sleep_s = _seconds_until_next(cfg.post_time, cfg.tz)
            logger.info(f"[OK] Sleeping {sleep_s}s until next run.")
            await asyncio.sleep(sleep_s)

            try:
                await run_once(cfg)
                logger.info("[OK] Playbook posted.")
            except Exception as e:
                logger.exception(f"[ERROR] Playbook run failed: {e}")

            # Safety buffer to avoid double posting if clocks drift
            await asyncio.sleep(5)

    asyncio.run(forever())
    return 0
