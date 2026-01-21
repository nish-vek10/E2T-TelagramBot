# morning_missive/src/missive/providers/calendar_tradingview.py

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo
import requests


@dataclass
class TVEvent:
    dt_utc: datetime
    country: str
    event: str
    importance: int

_ALLOWED = {"EU", "GB", "US", "JP", "CN", "AU", "NZ"}
_ALLOWED_IMP = {0, 1}   # 0=MEDIUM IMPACT, 1=HIGH IMPACT


def _parse_tv_date(ts) -> datetime | None:
    """
    TradingView may return `date` as:
      - int/float milliseconds since epoch
      - string milliseconds
      - ISO datetime string (e.g. 2026-01-15T13:30:00Z)
    Return UTC datetime or None.
    """
    if ts is None:
        return None

    # If numeric or numeric string → treat as milliseconds
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000, tz=ZoneInfo("UTC"))

    if isinstance(ts, str):
        s = ts.strip()

        # numeric string
        if s.isdigit():
            return datetime.fromtimestamp(int(s) / 1000, tz=ZoneInfo("UTC"))

        # ISO-ish string
        try:
            # handle trailing Z
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            return dt.astimezone(ZoneInfo("UTC"))
        except Exception:
            return None

    return None


def fetch_calendar_today_high_impact() -> List[TVEvent]:

    # today = datetime.now(ZoneInfo("UTC")).date()
    # start = f"{today.isoformat()}T00:00:00Z"
    # end   = f"{today.isoformat()}T23:59:59Z"

    now = datetime.now(ZoneInfo("UTC"))
    start = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    # end_dt = now.replace(hour=23, minute=59, second=59)
    end_dt = now + timedelta(hours=24)
    end = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "range": {"from": start, "to": end},
    }

    r = requests.post(
        "https://economic-calendar.tradingview.com/events",
        json=payload,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/economic-calendar/",
        },
        timeout=20,
    )

    r.raise_for_status()

    data = r.json()
    if isinstance(data, dict):
        js = data.get("events") or data.get("result") or []

    elif isinstance(data, list):
        js = data
    else:
        js = []

    def _to_int(v, default=-999):
        try:
            return int(v)
        except Exception:
            return default

    out: List[TVEvent] = []
    seen = set()

    for e in js:
        dt = _parse_tv_date(e.get("date"))
        if dt is None:
            continue

        cc = (e.get("country") or "").strip().upper()
        if cc not in _ALLOWED:
            continue

        title = (e.get("title") or "").strip()
        indicator = (e.get("indicator") or "").strip()
        event_text = title or indicator
        if not event_text:
            continue

        try:
            raw_imp = int(e.get("importance"))
        except Exception:
            raw_imp = -999

        # keep only medium/high (0/1) and drop -1 holidays/low
        if raw_imp not in _ALLOWED_IMP:
            continue

        # dedupe (country + event + minute)
        k = (cc, event_text.lower(), dt.strftime("%Y-%m-%d %H:%M"))
        if k in seen:
            continue
        seen.add(k)

        out.append(TVEvent(dt_utc=dt, country=cc, event=event_text, importance=raw_imp))

    out.sort(key=lambda x: x.dt_utc)
    return out


