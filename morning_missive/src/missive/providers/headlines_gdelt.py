from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List
import requests
import re
from missive.utils.text import shorten

@dataclass
class Headline:
    title: str
    tag: str

def _gdelt_ts(dt: datetime) -> str:
    return dt.astimezone(ZoneInfo("UTC")).strftime("%Y%m%d%H%M%S")

def _tag(domain: str) -> str:
    d = domain.lower()
    if "reuters.com" in d: return "RTRS"
    if "bloomberg.com" in d: return "BBG"
    if "cnbc.com" in d: return "CNBC"
    if "ft.com" in d: return "FT"
    if "wsj.com" in d: return "WSJ"
    return (d.split(".")[0].upper()[:8] if d else "NEWS")

_space_fix_replacements = [
    # 2 . 7 %  -> 2.7%
    (re.compile(r"(\d)\s*\.\s*(\d)"), r"\1.\2"),
    (re.compile(r"(\d)\s*%\s*"), r"\1%"),
    # 92 , 500 -> 92,500
    (re.compile(r"(\d)\s*,\s*(\d)"), r"\1,\2"),
    # 5 - Year -> 5-Year
    (re.compile(r"(\d)\s*-\s*([A-Za-z])"), r"\1-\2"),
    # U . S . -> U.S.
    (re.compile(r"\bU\s*\.\s*S\s*\.\b"), "U.S."),
    (re.compile(r"\bU\s*\.\s*K\s*\.\b"), "U.K."),
]

def clean_title(title: str) -> str:
    t = (title or "").strip()
    # Remove weird spacing around punctuation generally
    t = re.sub(r"\s+([,.:;!?%])", r"\1", t)  # "2 . 7 %" -> "2.7%"
    t = re.sub(r"([,.:;!?])\s+", r"\1 ", t)  # normalize after punctuation
    t = re.sub(r"\s{2,}", " ", t)  # collapse multi-spaces

    for rx, repl in _space_fix_replacements:
        t = rx.sub(repl, t)

    # Remove stray spaces around hyphen (words)
    t = re.sub(r"\s*-\s*", "-", t)  # "5 - Year" -> "5-Year"

    # Fix "2.7%in" -> "2.7% in"
    t = re.sub(r"(\d%)\s*([A-Za-z])", r"\1 \2", t)

    # Fix "U. S." / "U. K." variants that sneak through
    t = t.replace("U. S.", "U.S.").replace("U. K.", "U.K.")

    # Fix "USD / CHF" -> "USD/CHF"
    t = re.sub(r"\b([A-Z]{2,5})\s*/\s*([A-Z]{2,5})\b", r"\1/\2", t)

    return t


def fetch_headlines(*, query: str, tz: str, lookback_hours: int, limit: int, whitelist_domains: List[str]) -> List[Headline]:
    now = datetime.now(tz=ZoneInfo(tz))
    start = now - timedelta(hours=lookback_hours)

    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(max(limit * 6, 60)),  # pull more to filter/dedupe
        "startdatetime": _gdelt_ts(start),
        "enddatetime": _gdelt_ts(now),
        "sourcelang": "english",
        "sort": "HybridRel",
    }
    r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, timeout=20)
    r.raise_for_status()
    arts = (r.json().get("articles", []) or [])

    wl = [x.strip().lower() for x in whitelist_domains if x.strip()]
    out: List[Headline] = []
    seen = set()

    def ok_title(t: str) -> bool:
        # quick filter: drop empty + very short
        if not t or len(t) < 20:
            return False
        # drop titles with lots of non-ascii (often non-English)
        non_ascii = sum(1 for ch in t if ord(ch) > 127)
        return non_ascii <= 3

    def add(title: str, domain: str):
        key = title.lower().replace("—", "-").strip()
        key = key[:80]  # normalize duplicates
        if key in seen:
            return
        seen.add(key)
        out.append(Headline(shorten(clean_title(title), 135), _tag(domain)))


    # 1) Whitelist pass
    for a in arts:
        title = (a.get("title") or "").strip()
        domain = (a.get("domain") or "").strip().lower()
        if not ok_title(title):
            continue
        if wl and not any(domain.endswith(d) or d in domain for d in wl):
            continue
        add(title, domain)
        if len(out) >= limit:
            break

    # 2) STRICT MODE: no fallback to random domains
    # If whitelist yields too few, return what we have (renderer can add a note)
    return out
