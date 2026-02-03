# morning_missive/src/missive/bot/run.py

from __future__ import annotations

import sys
import os
from missive.config import Settings
from missive.providers.prices_oanda import fetch_prices
from missive.render.template import build_message
from missive.bot.scheduler import start_daily
from missive.bot.telegram_client import send_message

from missive.providers.calendar_tradingview import fetch_calendar_today_high_impact
from missive.providers.headlines_perplexity import fetch_market_pulse_and_headlines, fetch_todays_papers
from missive.storage.supabase_client import get_supabase
from missive.storage.save_missive import save_missive_to_supabase



def build_payload():
    """
    Returns (rendered_message, payload_parts) for saving to Supabase without re-parsing.
    """
    s = Settings()

    prices = fetch_prices(
        base_url=s.oanda_base_url,
        api_key=s.OANDA_API_KEY,
        account_id=s.OANDA_ACCOUNT_ID,
        instruments=s.instruments_list,
    )

    cal_events = fetch_calendar_today_high_impact()

    pulse, px_headlines = fetch_market_pulse_and_headlines()
    pulse_text = pulse.text.strip() if pulse.text else "AWAITING MACRO SIGNALS."
    headline_lines = [h.text for h in px_headlines]

    papers = fetch_todays_papers()
    papers_lines = papers.lines

    msg = build_message(
        tz=s.TZ,
        prices=prices,
        pulse_text=pulse_text,
        headline_lines=headline_lines,
        papers_lines=papers_lines,
        cal_events=cal_events,
    )

    parts = {
        "prices": prices,
        "pulse_text": pulse_text,
        "headline_lines": headline_lines,
        "papers_lines": papers_lines,
        "cal_events": cal_events,
    }
    return msg, parts


def build_once() -> str:
    msg, _ = build_payload()
    return msg


def post_once() -> None:
    s = Settings()
    msg, parts = build_payload()

    # Decide whether to save
    save_enabled = bool(s.MISSIVE_SAVE_SUPABASE)
    save_allowed_in_dry = bool(s.MISSIVE_SAVE_ON_DRY_RUN)

    should_save = save_enabled and (save_allowed_in_dry or (not s.MISSIVE_DRY_RUN))

    missive_id = None
    if should_save:
        supabase = get_supabase()
        missive_id = save_missive_to_supabase(
            supabase=supabase,
            tz=s.TZ,
            post_hour=s.POST_HOUR,
            post_minute=s.POST_MINUTE,
            telegram_chat_id=s.MISSIVE_CHAT_ID,
            rendered_text=msg,
            pulse_text=parts["pulse_text"],
            prices=parts["prices"],
            headline_lines=parts["headline_lines"],
            papers_lines=parts["papers_lines"],
            cal_events=parts["cal_events"],
            posted_to_telegram=(not s.MISSIVE_DRY_RUN and not s.MISSIVE_SAVE_ONLY),
        )
        print(f"[OK] Supabase saved missive_id={missive_id}")

    # DRY RUN behaviour remains, unless SAVE_ONLY is on (test mode)
    if s.MISSIVE_DRY_RUN or s.MISSIVE_SAVE_ONLY:
        print("\n========== MISSIVE DRY RUN ==========\n")
        print(msg)
        print("\n====================================\n")
        if s.MISSIVE_SAVE_ONLY:
            print("[OK] SAVE_ONLY=1 → Skipping Telegram send.")
        return

    # Live send (unchanged)
    send_message(
        s.MISSIVE_BOT_TOKEN,
        s.MISSIVE_CHAT_ID,
        msg,
        thread_id=(s.MISSIVE_THREAD_ID if s.MISSIVE_THREAD_ID > 0 else None),
    )

    print("[OK] Missive posted.")


def main() -> None:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "serve").lower()

    if mode == "once":
        post_once()
        return

    if mode == "serve":
        s = Settings()
        start_daily(tz=s.TZ, hour=s.POST_HOUR, minute=s.POST_MINUTE, job_fn=post_once)
        return

    raise SystemExit("Usage: python morning_missive/run_missive.py [once|serve]")

if __name__ == "__main__":
    main()
