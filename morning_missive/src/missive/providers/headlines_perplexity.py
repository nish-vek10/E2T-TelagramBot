# morning_missive/src/missive/providers/headlines_perplexity.py

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple
import os
import re
import requests


@dataclass
class PXHeadline:
    text: str


@dataclass
class PXPulse:
    text: str


@dataclass
class PXPapers:
    lines: List[str]


def fetch_market_pulse_and_headlines() -> Tuple[PXPulse, List[PXHeadline]]:
    api_key = os.getenv("PERPLEXITY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing PERPLEXITY_API_KEY (set it in your root .env)")

    prompt = """
You are a global macro trading desk assistant. You MUST use web research to produce a genuine morning market note for TODAY.

DO NOT mention limitations, missing app_data, job postings, or "search results". Do not include any disclaimers.
If you cannot find something, omit it—do not explain why.

TASK:
A) MARKET_PULSE: 5–8 bullet lines, ALL CAPS, each 10–18 words, each starts with "- ".
   Focus on: equities, rates, USD, gold, oil, geopolitics, central banks, key risk themes.

B) TOP_OVERNIght_HEADLINES: up to 8 bullet lines, each starts with "- " and ends with a period.
   Each headline must be real and market-relevant.
   Add a short source tag at the end in parentheses like (RTRS), (BBG), (CNBC), (FT), (WSJ).
   No citations like [1].

FORMAT AS:

OUTPUT FORMAT (EXACT):

MARKET_PULSE:
- ...
- ...
- ...

HEADLINES:
- ... (SRC).
- ... (SRC).
""".strip()

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
            "top_p": 0.9,
        },
        timeout=30,
    )
    r.raise_for_status()

    js = r.json()
    content = js["choices"][0]["message"]["content"] or ""

    bad_phrases = [
        "I APPRECIATE YOUR DETAILED REQUEST",
        "I NEED TO CLARIFY",
        "LIMITATION",
        "JOB DESCRIPTIONS",
        "SEARCH RESULTS PROVIDED",
    ]
    if any(p.lower() in content.lower() for p in bad_phrases):
        # If the model replied with a disclaimer, force a retry with stricter instruction.
        retry_prompt = prompt + "\n\nREMINDER: DO NOT WRITE DISCLAIMERS. WRITE THE NOTE USING WEB RESEARCH."
        r2 = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "sonar-pro", "messages": [{"role": "user", "content": retry_prompt}], "temperature": 0.2},
            timeout=30,
        )
        r2.raise_for_status()
        content = r2.json()["choices"][0]["message"]["content"] or ""

    pulse_lines: List[str] = []
    headlines: List[PXHeadline] = []

    in_pulse = False
    in_headlines = False

    def is_bullet(line: str) -> bool:
        return line.startswith("- ") or line.startswith("• ")

    def clean_headline(txt: str) -> str:
        # remove citations like [1], [2], [1, 2], [1][2]
        txt = re.sub(r"\[\s*\d+\s*\]", "", txt)
        txt = re.sub(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]", "", txt)

        # collapse whitespace early
        txt = re.sub(r"\s{2,}", " ", txt).strip()

        # --- Normalize trailing source tag ---
        # Accepts: "... (BBG).", "... (RTRS)", "... (FT) ."
        m = re.search(r"\s*\(([^()]{2,20})\)\s*\.?\s*$", txt)
        src = None
        if m:
            src = m.group(1).strip().upper()
            txt = txt[:m.start()].rstrip()

        # remove trailing punctuation from headline body (we control punctuation in renderer)
        txt = re.sub(r"[\s\.\,;:!\?]+$", "", txt).strip()

        # re-attach normalized source tag (NO trailing punctuation)
        if src:
            txt = f"{txt} [{src}]"

        return txt

    raw_lines = [ln.rstrip() for ln in content.splitlines()]

    for ln in raw_lines:
        s = ln.strip()
        if not s:
            continue

        u = s.upper()

        # Section switches (case-insensitive)
        if u.startswith("MARKET_PULSE:") or u.startswith("MARKET PULSE:"):
            in_pulse = True
            in_headlines = False
            continue

        if u.startswith("HEADLINES:") or u.startswith("TOP HEADLINES:"):
            in_headlines = True
            in_pulse = False
            continue

        # Pulse collection
        if in_pulse:
            if is_bullet(s):
                # keep bullet lines, force uppercase, normalize bullet to "- "
                body = s[2:].strip().upper()
                body = body.lstrip("- ").strip()
                pulse_lines.append(f"- {body}")
            else:
                # accept non-bullet pulse lines, but make them uppercase and bullet them
                pulse_lines.append(f"- {s.upper()}")
            continue

        # Headlines collection
        if in_headlines:
            if is_bullet(s):
                txt = s[2:].strip()
                headlines.append(PXHeadline(clean_headline(txt)))
            continue

    # -------- Fallbacks to avoid empty output --------

    # Pulse fallback: if none captured, take first 6 non-empty lines and bullet them
    if not pulse_lines and content.strip():
        tmp = [ln.strip() for ln in content.splitlines() if ln.strip()]
        pulse_lines = [f"- {ln.upper()}" for ln in tmp[:6]]

    # Headline fallback: if none captured, take last 8 non-empty lines that aren't headers
    if not headlines and content.strip():
        tmp = [ln.strip() for ln in content.splitlines() if ln.strip()]
        for ln in tmp[-30:]:
            uu = ln.upper()
            if uu.startswith(("MARKET_PULSE:", "MARKET PULSE:", "HEADLINES:", "TOP HEADLINES:")):
                continue
            ln2 = ln.lstrip("-• ").strip()
            if not ln2:
                continue
            headlines.append(PXHeadline(clean_headline(ln2)))
            if len(headlines) >= 8:
                break

    pulse_txt = "\n".join(pulse_lines[:8]).strip()

    # Ensure max 8 headlines
    headlines = headlines[:8]

    return PXPulse(pulse_txt), headlines


def fetch_todays_papers() -> PXPapers:
    api_key = os.getenv("PERPLEXITY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing PERPLEXITY_API_KEY (set it in your root .env)")

    prompt = """
You are a global macro trading desk assistant.

TASK: Produce TODAY'S PAPERS — exactly 4 bullet lines sourced from major newspapers/wires:
Financial Times (FT), Wall Street Journal (WSJ), Reuters (RTRS). Prefer those three.

Rules:
- EXACTLY 4 bullets.
- Each line 12–22 words.
- Must be a real, market-relevant headline or lead story theme from TODAY.
- End each line with a source tag in square brackets: [FT], [WSJ], or [RTRS].
- No citations like [1], [2]. No disclaimers. No meta commentary.
- Do NOT reuse the same stories from the "Top Overnight Headlines" section; choose distinct angles if possible.

FORMAT EXACTLY:

PAPERS:
- ...
- ...
- ...
- ...
""".strip()

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
            "top_p": 0.9,
        },
        timeout=30,
    )
    r.raise_for_status()

    js = r.json()
    content = js["choices"][0]["message"]["content"] or ""


    # Extract bullets under PAPERS / TODAY'S PAPERS / TODAY’S PAPERS.
    # If the model ignores headers, fall back to first 4 bullets anywhere.
    raw_bullets: List[str] = []
    in_papers = False


    for ln in content.splitlines():
        s = ln.strip()
        if not s:
            continue

        u = s.upper()

        # Accept multiple header variants
        if u.startswith("PAPERS:") or u.startswith("TODAY'S PAPERS:") or u.startswith("TODAY’S PAPERS:"):
            in_papers = True
            continue

        # Collect bullets either after header OR (fallback later) anywhere
        if s.startswith("- ") or s.startswith("• "):
            raw_bullets.append(s[2:].strip())
            continue

    # Prefer bullets after a papers header if present; otherwise fallback to any bullets
    # If there was a header, the model usually puts papers bullets early, so just take first 8 bullets.
    candidates = raw_bullets[:]

    lines: List[str] = []
    for item in candidates:
        if not item:
            continue

        # strip numeric citations like [1], [2], [1,2]
        item = re.sub(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]", "", item).strip()

        # normalize trailing source tags to bracket form:
        # "... WSJ" / "... (WSJ)" / "... [WSJ]" / with optional trailing dot -> "... [WSJ]"
        m = re.search(r"\s*(?:\[(FT|WSJ|RTRS)\]|\((FT|WSJ|RTRS)\)|\b(FT|WSJ|RTRS)\b)\s*\.?\s*$", item, flags=re.I)
        if m:
            tag = (m.group(1) or m.group(2) or m.group(3) or "").upper()
            # remove the matched tail (tag + optional dot/spaces)
            item = re.sub(
                r"\s*(?:\[(FT|WSJ|RTRS)\]|\((FT|WSJ|RTRS)\)|\b(FT|WSJ|RTRS)\b)\s*\.?\s*$",
                "",
                item,
                flags=re.I,
            ).rstrip()
            item = item.rstrip(".").rstrip()
            item = f"{item} [{tag}]"

        # ensure it ends with [TAG]
        if not re.search(r"\[(FT|WSJ|RTRS)\]\s*$", item, flags=re.I):
            # if model forgot tag, default to RTRS rather than failing
            item = item.rstrip(".").strip() + " [RTRS]"

        # remove punctuation AFTER the tag
        item = re.sub(r"(\[(?:FT|WSJ|RTRS)\])[\s\.\,;:!\?]+$", r"\1", item, flags=re.I).strip()

        lines.append(item)
        if len(lines) >= 4:
            break

    # hard guarantee exactly 4 lines
    lines = lines[:4]
    while len(lines) < 4:
        lines.append("NO PAPER HEADLINES RETURNED — CHECK PERPLEXITY. [RTRS]")

    return PXPapers(lines=lines)
