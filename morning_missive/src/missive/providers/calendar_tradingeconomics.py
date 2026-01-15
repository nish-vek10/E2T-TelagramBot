from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import List, Optional
from zoneinfo import ZoneInfo
import requests
import urllib.parse


@dataclass
class TEEvent:
    dt_utc: datetime
    country: str
    category: str
    event: str
    actual: str
    forecast: str
    previous: str
    importance: int


def _parse_dt(dt_str: str) -> Optional[datetime]:
    """
    TE returns ISO-like strings (e.g. 2023-04-03T14:00:00).
    Treat as UTC if no tz is supplied.
    """
    if not dt_str:
        return None
    try:
        # if TE gives no timezone, interpret as UTC (works well for desk notes)
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("UTC"))
    except Exception:
        return None


def fetch_calendar_today_high_impact(
    *,
    api_key: str,
    countries: List[str],
    importance: int = 3,
) -> List[TEEvent]:
    """
    Pull today's high-impact events for selected countries.

    Uses the documented endpoint:
      /calendar/country/<country>?c=<key>&importance=3 :contentReference[oaicite:5]{index=5}

    We call it once per country, then filter to today's UTC date.
    """
    today_utc = datetime.now(ZoneInfo("UTC")).date()
    out: List[TEEvent] = []

    for ctry in countries:
        # docs example uses lowercase and url encoding for spaces
        ctry_path = urllib.parse.quote(ctry.lower())

        url = f"https://api.tradingeconomics.com/calendar/country/{ctry_path}"
        params = {"c": api_key, "importance": str(importance)}

        r = requests.get(url, params=params, timeout=25)

        # Handle country-level permission blocks cleanly (TE often blocks some countries by plan)
        if r.status_code == 403:
            print(f"[TE] 403 blocked country: {ctry}")
            # Skip this country but continue others
            # (We intentionally do not raise; the missive should still send)
            continue

        # Other errors should still surface
        r.raise_for_status()

        js = r.json() or []

        for row in js:
            dt = _parse_dt(row.get("Date") or row.get("date") or "")
            if not dt:
                continue
            if dt.date() != today_utc:
                continue

            imp = int(row.get("Importance") or row.get("importance") or 0)
            if imp != importance:
                continue

            out.append(
                TEEvent(
                    dt_utc=dt,
                    country=str(row.get("Country") or ctry),
                    category=str(row.get("Category") or ""),
                    event=str(row.get("Event") or ""),
                    actual=str(row.get("Actual") or ""),
                    forecast=str(row.get("Forecast") or ""),
                    previous=str(row.get("Previous") or ""),
                    importance=imp,
                )
            )

    out.sort(key=lambda x: x.dt_utc)
    return out
