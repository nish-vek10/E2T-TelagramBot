from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Tuple

from missive.providers.prices_oanda import OandaPrice
from missive.providers.calendar_tradingview import TVEvent


RE_SRC_TAG = re.compile(r"\s*(\[[A-Z0-9_\-]+\])\s*$")


def _extract_src_tag(line: str) -> tuple[str, Optional[str]]:
    """
    Returns (body, tag) where tag is like [RTRS] if present.
    """
    x = (line or "").strip()
    m = RE_SRC_TAG.search(x)
    if not m:
        return x, None
    tag = m.group(1)
    body = x[: m.start()].rstrip()
    return body, tag


def _alias(inst: str) -> str:
    return {
        "SPX500_USD": "SP500",
        "NAS100_USD": "NAS100",
        "XAU_USD": "XAUUSD",
        "WTICO_USD": "WTI",
        "BTC_USD": "BTC",
        "ETH_USD": "ETH",
        "EUR_USD": "EURUSD",
        "GBP_USD": "GBPUSD",
        "USD_JPY": "USDJPY",
    }.get(inst, inst)


def _decimals_for(inst: str) -> int:
    if inst in ("SPX500_USD", "NAS100_USD", "XAU_USD", "BTC_USD", "ETH_USD"):
        return 2
    if inst in ("WTICO_USD",):
        return 2
    if inst in ("EUR_USD", "GBP_USD"):
        return 4
    if inst in ("USD_JPY",):
        return 2
    return 2


def _fmt_asset(inst: str, v: float | None) -> Optional[str]:
    if v is None:
        return None
    dp = _decimals_for(inst)
    return f"{v:,.{dp}f}"


def _impact_bar(imp: int) -> str:
    return "★★★" if imp == 1 else "★★☆"


def _flag_tag(cc: str) -> str:
    cc = (cc or "").upper()
    return {
        "EU": "🇪🇺 EU",
        "GB": "🇬🇧 UK",
        "US": "🇺🇸 US",
        "CN": "🇨🇳 CN",
        "JP": "🇯🇵 JP",
        "AU": "🇦🇺 AU",
        "NZ": "🇳🇿 NZ",
    }.get(cc, cc)


def _session_bucket(dt_utc: datetime) -> str:
    t = dt_utc.astimezone(ZoneInfo("UTC"))
    h = t.hour
    m = t.minute
    if h < 7:
        return "ASIA"
    if (h < 13) or (h == 13 and m == 0):
        return "EU"
    if (h < 22) or (h == 22 and m == 0):
        return "US"
    return "POST"


def _fmt_time_gmt(dt_utc: datetime) -> str:
    return dt_utc.astimezone(ZoneInfo("UTC")).strftime("%H:%M")


def save_missive_to_supabase(
    *,
    supabase,
    tz: str,
    post_hour: int,
    post_minute: int,
    telegram_chat_id: str,
    rendered_text: str,
    pulse_text: str,
    prices: Dict[str, OandaPrice],
    headline_lines: List[str],
    papers_lines: List[str],
    cal_events: List[TVEvent],
    posted_to_telegram: bool,
) -> str:
    """
    Creates/updates today's missive (by London date) and replaces child rows.
    Returns missive_id (uuid string).
    """
    now_local = datetime.now(ZoneInfo(tz))
    post_date = now_local.date().isoformat()

    # 1) Upsert master row by post_date
    master_payload = {
        "post_date": post_date,
        "tz": tz,
        "asof_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "post_hour": post_hour,
        "post_minute": post_minute,
        "telegram_chat_id": str(telegram_chat_id),
        "posted_to_telegram": bool(posted_to_telegram),
        "rendered_text": rendered_text,
    }

    up = supabase.table("missives").upsert(master_payload, on_conflict="post_date").execute()
    # Supabase returns list rows in .data
    missive_id = up.data[0]["id"]

    # 2) Clear children (idempotent refresh)
    supabase.table("missive_market_pulse_lines").delete().eq("missive_id", missive_id).execute()
    supabase.table("missive_key_rates").delete().eq("missive_id", missive_id).execute()
    supabase.table("missive_headlines").delete().eq("missive_id", missive_id).execute()
    supabase.table("missive_focus_events").delete().eq("missive_id", missive_id).execute()
    supabase.table("missive_papers").delete().eq("missive_id", missive_id).execute()

    # 3) Insert pulse lines (split bullets/lines robustly)
    pulse_lines: List[str] = []
    for ln in (pulse_text or "").splitlines():
        x = ln.strip()
        if not x:
            continue
        pulse_lines.append(x)

    if pulse_lines:
        rows = [{"missive_id": missive_id, "line_no": i + 1, "text": t} for i, t in enumerate(pulse_lines)]
        supabase.table("missive_market_pulse_lines").insert(rows).execute()

    # 4) Insert key rates (use daily_close like your template)
    order = [
        "SPX500_USD",
        "NAS100_USD",
        "XAU_USD",
        "WTICO_USD",
        "BTC_USD",
        "ETH_USD",
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
    ]

    rate_rows = []
    rank = 0
    for inst in order:
        p = prices.get(inst)
        if not p:
            continue
        v = p.daily_close
        rank += 1
        rate_rows.append(
            {
                "missive_id": missive_id,
                "rank": rank,
                "symbol": _alias(inst),
                "instrument": inst,
                "price": v,
                "display": _fmt_asset(inst, v),
                "source": "oanda",
            }
        )

    # any extras
    for inst, p in prices.items():
        if inst in order:
            continue
        v = p.daily_close
        rank += 1
        rate_rows.append(
            {
                "missive_id": missive_id,
                "rank": rank,
                "symbol": _alias(inst),
                "instrument": inst,
                "price": v,
                "display": _fmt_asset(inst, v),
                "source": "oanda",
            }
        )

    if rate_rows:
        supabase.table("missive_key_rates").insert(rate_rows).execute()

    # 5) Insert headlines (max 8 like your template)
    hl_rows = []
    for i, raw in enumerate((headline_lines or [])[:8], start=1):
        body, tag = _extract_src_tag(raw)
        body = body.strip()
        if not body:
            continue
        hl_rows.append(
            {"missive_id": missive_id, "rank": i, "headline": body, "source_tag": tag, "raw_line": raw}
        )
    if hl_rows:
        supabase.table("missive_headlines").insert(hl_rows).execute()

    # 6) Insert focus events by session (max 10 each like your template)
    sess_counts = {"ASIA": 0, "EU": 0, "US": 0, "POST": 0}
    ev_rows = []
    for e in (cal_events or []):
        sess = _session_bucket(e.dt_utc)
        if sess_counts[sess] >= 10:
            continue
        sess_counts[sess] += 1

        imp = int(e.importance or 0)
        ev_rows.append(
            {
                "missive_id": missive_id,
                "session": sess,
                "rank": sess_counts[sess],
                "dt_utc": e.dt_utc.isoformat(),
                "time_gmt": _fmt_time_gmt(e.dt_utc),
                "country": (e.country or "").upper(),
                "flag": _flag_tag(e.country),
                "importance": imp,
                "impact_bar": _impact_bar(imp),
                "event": e.event,
            }
        )
    if ev_rows:
        supabase.table("missive_focus_events").insert(ev_rows).execute()

    # 7) Insert papers (max 4 like your template)
    pp_rows = []
    for i, raw in enumerate((papers_lines or [])[:4], start=1):
        body, tag = _extract_src_tag(raw)
        body = body.strip()
        if not body:
            continue
        pp_rows.append({"missive_id": missive_id, "rank": i, "text": body, "source_tag": tag, "raw_line": raw})

    # Ensure 4 rows if you want strict “always 4”
    while len(pp_rows) < 4:
        i = len(pp_rows) + 1
        pp_rows.append({"missive_id": missive_id, "rank": i, "text": "N/A", "source_tag": "[RTRS]", "raw_line": "N/A [RTRS]"})

    supabase.table("missive_papers").insert(pp_rows[:4]).execute()

    return str(missive_id)
