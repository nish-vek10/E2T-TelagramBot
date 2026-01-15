from __future__ import annotations
from dataclasses import dataclass
from typing import List
import requests
import os
import re


@dataclass
class PXHeadline:
    text: str


@dataclass
class PXPulse:
    text: str


def fetch_market_pulse_and_headlines() -> tuple[PXPulse, List[PXHeadline]]:
    api_key = os.getenv("PERPLEXITY_API_KEY")
    assert api_key, "Missing PERPLEXITY_API_KEY"

    prompt = """
You are a professional macro trading desk assistant writing a MORNING MISSIVE.

OUTPUT REQUIREMENTS (STRICT):
1) MARKET_PULSE must be 5-8 BULLET LINES.
2) EACH LINE MUST BE UPPERCASE.
3) EACH LINE MUST START WITH "- " (dash + space).
4) EACH LINE MUST BE 10–18 WORDS.
5) NO CITATIONS. NO [1]. NO SOURCES IN PULSE.

Then provide HEADLINES:
- Up to 8 bullets
- Each bullet MUST end with a period.
- NO CITATIONS like [1], [2].
- Keep factual and concise.

FORMAT AS:

MARKET_PULSE:
- LINE 1
- LINE 2
- LINE 3
- LINE 4
- LINE 5
- LINE 6

HEADLINES:
- HEADLINE 1.
- HEADLINE 2.
- ...
"""

    r = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "sonar-pro",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=30,
    )
    r.raise_for_status()

    content = r.json()["choices"][0]["message"]["content"]

    pulse_txt = ""
    headlines = []

    lines = [ln.rstrip() for ln in content.splitlines()]

    in_pulse = False
    in_headlines = False

    for ln in lines:
        s = ln.strip()

        if s.startswith("MARKET_PULSE:"):
            in_pulse = True
            in_headlines = False
            pulse_txt = ""
            continue

        if s.startswith("HEADLINES:"):
            in_headlines = True
            in_pulse = False
            continue

        if in_pulse:
            if s.startswith("- "):
                pulse_txt = (pulse_txt + "\n" + s).strip() if pulse_txt else s
            elif s and not s.startswith("- "):
                # if model gives a non-bulleted pulse line, still keep it
                pulse_txt = (pulse_txt + "\n" + s.upper()).strip() if pulse_txt else s.upper()
            continue

        elif in_headlines and s.startswith("- "):
            txt = s[2:].strip()
            txt = re.sub(r"\[\s*\d+\s*\]", "", txt)
            txt = re.sub(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]", "", txt)
            txt = re.sub(r"\s{2,}", " ", txt).strip()
            txt = txt.rstrip(".").strip() + "."
            headlines.append(PXHeadline(txt))

    # Safety: if pulse came back as a single blob, force 6 uppercase bullet lines
    if pulse_txt and "\n" not in pulse_txt and len(pulse_txt.split()) > 20:
        words = pulse_txt.upper().split()
        step = max(8, len(words) // 6)
        lines_out = []
        for i in range(0, len(words), step):
            seg = " ".join(words[i:i + step]).strip()
            if seg:
                lines_out.append(f"- {seg[:110]}")
            if len(lines_out) == 6:
                break
        pulse_txt = "\n".join(lines_out)

    return PXPulse(pulse_txt), headlines
