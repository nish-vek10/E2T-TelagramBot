# daily_playbook/src/playbook/providers/geopolitics_headlines.py
from __future__ import annotations

import httpx
from datetime import datetime
from zoneinfo import ZoneInfo

from playbook.config import PlaybookConfig


PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"


def build_playbook_prompt(*, now_local_str: str) -> str:
    return f"""
You are writing a DAILY MACRO & GEOPOLITICAL TRADING PLAYBOOK for active traders.

Date (local): {now_local_str}

STYLE:
- Professional desk note, punchy, actionable
- UK spelling
- No fluff, no long paragraphs

HARD OUTPUT TEMPLATE (must follow exactly):

Daily Macro & Trading Playbook – <DATE>
🟢 Risk-On: <one line>
🔴 Risk-Off: <one line>

Pick 4 to 5 EVENTS (macro + geopolitical). For EACH EVENT:
EVENT X: <Event title>
Context:
- <bullet 1>
- <bullet 2>
- <bullet 3>

Then provide EXACTLY 3 scenario rows under each event in this row format (one row per line):
• <Headline>
  - Focus: <...>
  - Rationale: <...>

RULES FOR THE 3 ROWS:
- Headline: short, like a wire headline (no quotes needed)
- Focus: describe likely directional moves (NOT advice). Example: "Equities firmer; yields higher; gold softer"
- Rationale: 6–10 words

CONSTRAINTS:
- Write "Context:" on its own line (not on the event line).
- Do NOT include “Key Markets & Levels” section
- Do NOT include numeric citations like [1] or [2]
- You MAY use source tags only at the end of headlines inside parentheses, e.g. (Reuters), (FT), (WSJ) — optional
- Keep formatting Telegram-friendly: headings on their own line, blank line between sections
- Do NOT give trading instructions. Do NOT use "Buy/Sell/Long/Short". Use neutral market language only.
- Do NOT include sentiment column.
- Exactly 3 rows per event.


Now produce today's playbook.
""".strip()


def fetch_daily_playbook(cfg: PlaybookConfig) -> str:
    now = datetime.now(ZoneInfo(cfg.tz))
    now_str = now.strftime("%A %d %B %Y, %H:%M %Z")

    prompt = build_playbook_prompt(now_local_str=now_str)

    headers = {
        "Authorization": f"Bearer {cfg.perplexity_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": cfg.perplexity_model,
        "messages": [
            {"role": "system", "content": "You are a precise, professional market strategist."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    with httpx.Client(timeout=45) as client:
        r = client.post(PERPLEXITY_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    # Perplexity-style response typically resembles OpenAI chat.completions
    try:
        text = data["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Unexpected Perplexity response shape: {e}. Raw keys={list(data.keys())}")

    return text.strip()
