from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List

from missive.providers.prices_oanda import OandaPrice
from missive.providers.calendar_tradingview import TVEvent


def _fmt(v: float | None, dp: int = 2) -> str:
    return "N/A" if v is None else f"{v:,.{dp}f}"

def _get(prices: Dict[str, OandaPrice], inst: str) -> float | None:
    p = prices.get(inst)
    if not p:
        return None
    return p.live_mid if p.live_mid is not None else p.daily_close

def _alias(inst: str) -> str:
    # Desk-friendly names
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
    # sensible decimals by asset type
    if inst in ("SPX500_USD", "NAS100_USD", "XAU_USD", "BTC_USD", "ETH_USD"):
        return 2
    if inst in ("WTICO_USD",):
        return 2
    if inst in ("EUR_USD", "GBP_USD"):
        return 4
    if inst in ("USD_JPY",):
        return 2
    return 2


def _fmt_asset(inst: str, v: float | None) -> str:
    if v is None:
        return "N/A"
    dp = _decimals_for(inst)
    return f"{v:,.{dp}f}"


def _pricing_table(prices: Dict[str, OandaPrice]) -> str:
    # preferred order
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

    rows = []
    for inst in order:
        p = prices.get(inst)
        if not p:
            continue
        v = p.daily_close
        rows.append((_alias(inst), _fmt_asset(inst, v)))

    # include any extra instruments (not in order)
    for inst, p in prices.items():
        if inst in order:
            continue
        v = p.daily_close
        rows.append((_alias(inst), _fmt_asset(inst, v)))

    if not rows:
        return "N/A"

    name_w = max(len(a) for a, _ in rows)
    px_w = max(len(b) for _, b in rows)

    # Build a monospace table
    lines = []
    for a, b in rows:
        lines.append(f"{a:<{name_w}}  {b:>{px_w}}")
    return "```\n" + "\n".join(lines) + "\n```"


def _fmt_time_gmt(dt_utc: datetime) -> str:
    # 24h format in GMT (e.g., 13:30)
    return dt_utc.astimezone(ZoneInfo("UTC")).strftime("%H:%M")

def _impact_bar(imp: int) -> str:
    return "███" if imp == 1 else "██ "

def _flag_tag(cc: str) -> str:
    cc = (cc or "").upper()
    return {
        "GB": "🇬🇧 UK",
        "US": "🇺🇸 US",
        "CN": "🇨🇳 CN",
        "JP": "🇯🇵 JP",
        "AU": "🇦🇺 AU",
        "NZ": "🇳🇿 NZ",
    }.get(cc, cc)

def _session_bucket(dt_utc: datetime) -> str:
    # GMT buckets (simple + desk-friendly)
    h = dt_utc.astimezone(ZoneInfo("UTC")).hour
    if h < 7:
        return "ASIA"
    if h < 13:
        return "EU"
    return "US"

def _render_calendar_blocks(cal_events: List["TVEvent"]) -> tuple[str, str]:
    # TradingView calendar feed is best used for focus events by time.
    # For now: major events = list of event names; data releases = N/A (no reliable A/F/P).
    if not cal_events:
        return ("N/A", "N/A")

    major = []
    seen = set()
    for e in cal_events:
        key = (e.country, e.event)
        if key in seen:
            continue
        seen.add(key)
        major.append(f"{e.country}: {e.event}")
        if len(major) >= 12:
            break

    return ("\n".join(major) if major else "N/A", "N/A")


def _render_focus_sessions(cal_events: List["TVEvent"]) -> tuple[str, str, str]:
    if not cal_events:
        return ("N/A", "N/A", "N/A")

    eu, us, asia = [], [], []
    for e in cal_events:
        t = _fmt_time_gmt(e.dt_utc)
        cc_disp = _flag_tag(e.country)
        bar = _impact_bar(int(e.importance or 0))
        line = f"{t} — {cc_disp} {bar}: {e.event}"

        bucket = _session_bucket(e.dt_utc)
        if bucket == "ASIA":
            asia.append(line)
        elif bucket == "EU":
            eu.append(line)
        else:
            us.append(line)

    return (
        "\n".join(eu[:10]) if eu else "N/A",
        "\n".join(us[:10]) if us else "N/A",
        "\n".join(asia[:10]) if asia else "N/A",
    )


def build_message(
    *,
    tz: str,
    prices: Dict[str, OandaPrice],
    pulse_text: str,
    headline_lines: List[str],
    cal_events: List[TVEvent],
) -> str:

    now = datetime.now(tz=ZoneInfo(tz))
    date_str = now.strftime("%a %d %b %Y").upper()

    pricing_block = _pricing_table(prices)

    hl_lines = []
    for x in headline_lines[:8]:
        x = x.rstrip(".")
        hl_lines.append(f"• {x}.")

    if not hl_lines:
        hl_lines = ["• NO HEADLINES RETURNED — CHECK PERPLEXITY"]

    eu_block, us_block, asia_block = _render_focus_sessions(cal_events)

    if eu_block == "N/A" and us_block == "N/A" and asia_block == "N/A":
        # user-friendly fallback message
        eu_block = "NO MED/HIGH-IMPACT EVENTS IN NEXT WINDOW."
        us_block = "NO MED/HIGH-IMPACT EVENTS IN NEXT WINDOW."
        asia_block = "NO MED/HIGH-IMPACT EVENTS IN NEXT WINDOW."


    msg = f"""\
MORNING MISSIVE + DAILY PLAYBOOK — {date_str}

--- MARKET PULSE ---
{pulse_text}

--- KEY OVERNIGHT RATES ---
{pricing_block}

--- TOP OVERNIGHT HEADLINES ---
{chr(10).join(hl_lines)}

--- FOCUS EVENTS — TODAY (GMT) ---

ASIA / LATE:
{asia_block}

EU SESSION:
{eu_block}

US SESSION:
{us_block}


TODAY’S PAPERS (OPTIONAL)
N/A

— TRADING DESK / STAY DISCIPLINED INTO THE DATA WINDOWS.
"""
    return msg.strip()
