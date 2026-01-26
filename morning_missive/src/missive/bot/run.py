# morning_missive/src/missive/bot/run.py

from __future__ import annotations

import sys
from missive.config import Settings
from missive.providers.prices_oanda import fetch_prices
from missive.render.template import build_message
from missive.bot.scheduler import start_daily
from missive.bot.telegram_client import send_message

from missive.providers.calendar_tradingview import fetch_calendar_today_high_impact
from missive.providers.headlines_perplexity import fetch_market_pulse_and_headlines, fetch_todays_papers


def build_once() -> str:
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

    return build_message(
        tz=s.TZ,
        prices=prices,
        pulse_text=pulse_text,
        headline_lines=headline_lines,
        papers_lines=papers_lines,
        cal_events=cal_events,
    )


def post_once() -> None:
    s = Settings()
    msg = build_once()

    if s.MISSIVE_DRY_RUN:
        print("\n========== MISSIVE DRY RUN (NOT POSTING) ==========\n")
        print(msg)
        print("\n==================================================\n")
        return

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
