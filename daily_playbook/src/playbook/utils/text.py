# daily_playbook/src/playbook/utils/text.py
from __future__ import annotations

import re


_CITATION_BLOCK = re.compile(r"\[(?:\d+\s*)+\]")          # [1] or [1 2 3]
_CITATION_MULTI = re.compile(r"(?:\[\d+\]){2,}")          # [1][2][5]
_CITATION_SINGLE = re.compile(r"\[\d+\]")                 # [1]


def strip_citations(s: str) -> str:
    if not s:
        return ""
    out = s
    out = _CITATION_MULTI.sub("", out)
    out = _CITATION_BLOCK.sub("", out)
    out = _CITATION_SINGLE.sub("", out)
    # clean leftover double spaces before punctuation
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    return out.strip()


def clean_text(s: str) -> str:
    s = (s or "").strip()
    s = strip_citations(s)
    s = ensure_section_breaks(s)
    s = "\n".join(line.rstrip() for line in s.splitlines())
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def ensure_section_breaks(s: str) -> str:
    """
    Force headings onto new lines if the model puts them mid-line.
    """
    if not s:
        return ""

    tokens = [
        "Daily Macro & Trading Playbook",
        "🟢 Risk-On",
        "🔴 Risk-Off",
        "EVENT",
        "INTRADAY CHEAT SHEET",
        "TODAY’S MARKET SENTIMENT SNAPSHOT",
    ]

    out = s

    # Ensure major tokens start on new lines
    for t in tokens:
        out = out.replace(f" {t}", f"\n\n{t}")
        out = out.replace(f".{t}", f".\n\n{t}")
        out = out.replace(f") {t}", f")\n\n{t}")

    return out

