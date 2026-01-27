# daily_playbook/src/playbook/render/template.py
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from playbook.utils.text import clean_text

# --- Regex helpers ---
RE_EVENT = re.compile(r"^EVENT\s+(\d+):\s*(.+)$", re.IGNORECASE)
RE_CONTEXT = re.compile(r"^Context:\s*$", re.IGNORECASE)

RE_ROW = re.compile(
    r"^(?:Headline:\s*)?(?P<headline>.+?)\s*\|\s*(?P<trade>.+?)\s*\|\s*(?P<rat>.+?)\s*\|\s*(?P<sent>.*)$"
)

SENT_TOKENS = ("🟢 Risk-On", "🔴 Risk-Off", "⚠️ Mixed")

# --- Handle different dash characters the model may use (looks like "-" but isn't) ---
_DASHES = r"\-\u2010\u2011\u2012\u2013\u2212"  # hyphen, hyphen variants, en-dash, minus

RE_FOCUS_LINE = re.compile(rf"^[{_DASHES}]\s*(?:focus|trade|market reaction)\s*:\s*(.+)$", re.IGNORECASE)
RE_RATIONALE_LINE = re.compile(rf"^[{_DASHES}]\s*rationale\s*:\s*(.+)$", re.IGNORECASE)


# ---------------- MarkdownV2 escaping ----------------
_MDv2_SPECIALS = r"_*[]()~`>#+-=|{}.!\\"

def mdv2_escape(text: str) -> str:
    if text is None:
        return ""
    # Escape all special characters for MarkdownV2
    return re.sub(rf"([{re.escape(_MDv2_SPECIALS)}])", r"\\\1", str(text))

def mdv2_bold(text: str) -> str:
    return f"*{mdv2_escape(text)}*"

def mdv2_italic(text: str) -> str:
    return f"_{mdv2_escape(text)}_"


# ---------------- Normalisation ----------------
def _force_blank_line_before_tokens(text: str, tokens: list[str]) -> str:
    out = text
    for t in tokens:
        out = re.sub(rf"(?<!\n)\s+({re.escape(t)})", r"\n\n\1", out)
    return out

def _normalise_header_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for ln in lines:
        ln = ln.strip()

        # --- Emoji token normalisation (model may include emojis) ---
        # Convert emoji-prefixed headings into canonical tokens the parser expects.
        ln = re.sub(r"^\s*🌍\s*EVENT\b", "EVENT", ln, flags=re.IGNORECASE)
        ln = re.sub(r"^\s*📝\s*CONTEXT\s*:\s*", "Context:", ln, flags=re.IGNORECASE)

        # --- If Context: is appended to an EVENT line, split it onto its own line ---
        # e.g. "EVENT 1: ... Context:"  -> "EVENT 1: ...\nContext:"
        ln = re.sub(r"\s+Context\s*:\s*", "\nContext:", ln, flags=re.IGNORECASE)

        # Also handle emoji context used inline (rare):
        ln = re.sub(r"\s+📝\s*CONTEXT\s*:\s*", "\nContext:", ln, flags=re.IGNORECASE)

        # Convert emoji scenario marker into canonical bullet marker
        ln = re.sub(r"^\s*🧩\s*", "• ", ln)

        # If a scenario line contains inline "- Focus:" and "- Rationale:" on the same line,
        # force them onto their own lines.
        ln = re.sub(r"\s+-\s*Focus\s*:", "\n- Focus:", ln, flags=re.IGNORECASE)
        ln = re.sub(r"\s+-\s*Rationale\s*:", "\n- Rationale:", ln, flags=re.IGNORECASE)

        # Fix cases where a context bullet ends then "Headline:" continues same line
        ln = ln.replace(" pre-Fed Headline:", "\nHeadline:")
        ln = ln.replace(" odds Headline:", "\nHeadline:")
        ln = ln.replace(" positioning Headline:", "\nHeadline:")
        ln = ln.replace(" shadow Headline:", "\nHeadline:")
        ln = ln.replace(" divergence Headline:", "\nHeadline:")

        # Force critical tokens onto their own lines
        ln = ln.replace(" Headline | Trade | Rationale | Sentiment", "\nHeadline | Trade | Rationale | Sentiment")

        # If a line contains a pipe-row after some text (e.g., context bullet + row),
        # split it so the row starts on a new line.
        if " | " in ln and not ln.startswith("Headline | Trade | Rationale | Sentiment"):
            # split at the first occurrence of a likely row start
            parts = ln.split(" | ")
            if len(parts) >= 4:
                # rebuild the row from the last 4 columns
                row = " | ".join(parts[-4:])
                prefix = " | ".join(parts[:-4]).strip()
                if prefix:
                    ln = prefix + "\n" + row
                else:
                    ln = row

        # Force scenario markers onto new lines if Perplexity collapses them into context
        ln = re.sub(r"\s+•\s*", "\n• ", ln)
        ln = re.sub(r"\s+-\s*Trade:", "\n- Trade:", ln)
        ln = re.sub(r"\s+-\s*FOCUS:", "\n- FOCUS:", ln)
        ln = re.sub(r"\s+-\s*Market Reaction:", "\n- Market Reaction:", ln)
        ln = re.sub(r"\s+-\s*RATIONALE:", "\n- RATIONALE:", ln)

        # Split if we inserted a newline above
        if "\n" in ln:
            out.extend([x.strip() for x in ln.split("\n") if x.strip()])
        else:
            out.append(ln)
    return out


def _parse_and_format(text: str) -> str:
    lines = [l.rstrip() for l in text.splitlines()]
    lines = _normalise_header_lines(lines)

    formatted: list[str] = []
    after_context = False

    def flush_blank():
        if formatted and formatted[-1] != "":
            formatted.append("")

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        # Keep the top block
        if line.startswith("Daily Macro & Trading Playbook"):
            formatted.append(line)
            continue
        if line.startswith("🟢 Risk-On:") or line.startswith("🔴 Risk-Off:"):
            formatted.append(line)
            continue

        # Event heading
        m_ev = RE_EVENT.match(line)
        if m_ev:
            flush_blank()
            formatted.append(f"EVENT {m_ev.group(1)}: {m_ev.group(2)}")
            after_context = False
            continue

        # Context marker
        if RE_CONTEXT.match(line):
            formatted.append("Context:")
            after_context = True
            continue

        # Context bullets (ONLY "-" bullets; "•" belongs to scenarios)
        if after_context and line.startswith("-"):
            bullet = line.lstrip("-").strip()
            formatted.append(f"- {bullet}")
            continue

        # Table header line
        if line == "Headline | Trade | Rationale | Sentiment":
            formatted.append(line)
            continue

        # Pipe row
        m_row = RE_ROW.match(line)
        if m_row:
            headline = m_row.group("headline").strip()
            trade = m_row.group("trade").strip()
            rat = m_row.group("rat").strip()
            sent = (m_row.group("sent") or "").strip()

            if not sent:
                joined = f"{headline} {trade} {rat}"
                found = next((t for t in SENT_TOKENS if t in joined), "")
                sent = found

            if not sent:
                sent = "⚠️ Mixed"

            for t in SENT_TOKENS:
                headline = headline.replace(t, "").strip()
                trade = trade.replace(t, "").strip()
                rat = rat.replace(t, "").strip()

            formatted.append(f"{headline} | {trade} | {rat} | {sent}")
            continue

        formatted.append(line)

    out = "\n".join(formatted)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


# ---------------- Rendering (MarkdownV2) ----------------
def _format_date_header() -> str:
    dt = datetime.now(ZoneInfo("Europe/London"))
    return dt.strftime("%a %d %b %Y").upper()


def _truncate_events(lines: list[str]) -> list[str]:
    """
    For each EVENT block:
    - keep at most 3 context bullets
    - keep at most 3 scenario rows (pipe rows)
    - drop everything else (including stray bullets/cards)
    """
    out = []
    in_event = False
    in_context = False
    context_n = 0
    row_n = 0

    for ln in lines:
        line = ln.strip()
        if not line:
            continue

        if line.startswith("EVENT "):
            in_event = True
            in_context = False
            context_n = 0
            row_n = 0
            out.append(line)
            continue

        if not in_event:
            out.append(line)
            continue

        if line in ("Context:", "📝CONTEXT:"):
            in_context = True
            out.append(line)
            continue

        # context bullets
        if in_context and line.startswith("- "):
            if context_n < 3:
                out.append(line)
                context_n += 1
            continue

        # Stop context once we hit first scenario headline
        if in_context and line.startswith("• "):
            in_context = False

        # Keep scenario headline bullets (max 3)
        if line.startswith("• "):
            if row_n < 3:
                out.append(line)
                row_n += 1
            continue

        # Keep the two scenario detail lines under each headline
        if RE_FOCUS_LINE.match(line) or RE_RATIONALE_LINE.match(line):
            out.append(line)
            continue

        # Also allow indented versions (some models indent with spaces)
        norm = line.lstrip()
        if RE_FOCUS_LINE.match(norm) or RE_RATIONALE_LINE.match(norm):
            out.append(norm)  # normalise
            continue

        # ignore everything else inside event
        continue

    return out


def render_playbook(raw_text: str) -> str:
    raw = clean_text(raw_text)
    body = _parse_and_format(raw)

    # Enforce clean event structure: 3 context bullets + 3 scenario rows
    lines = _truncate_events(body.splitlines())

    day_line = _format_date_header()

    out_lines: list[str] = []
    out_lines.append(mdv2_bold("📘 DAILY MACRO PLAYBOOK"))
    out_lines.append(mdv2_bold(f"📅 {day_line}"))
    out_lines.append("────────────")

    in_event = False
    last_was_context = False
    printed_risk_block = False

    for ln in lines:
        line = ln.strip()
        if not line:
            continue

        # Drop stray tokens
        if line in ("🟢 Risk-On", "🔴 Risk-Off", "⚠️ Mixed", "🟢 Risk\\-On", "🔴 Risk\\-Off"):
            continue

        # Title with a descriptive subtitle
        if line.startswith("Daily Macro & Trading Playbook"):
            out_lines.append(
                mdv2_bold("Daily Macro & Trading Playbook with Risk Sentiments Explained")
            )
            continue

        # Risk lines (keep as plain) + add separator after risk block (once)
        if line.startswith("🟢 Risk-On:"):
            out_lines.append(mdv2_escape(line))
            printed_risk_block = True
            continue

        if line.startswith("🔴 Risk-Off:"):
            out_lines.append(mdv2_escape(line))
            if printed_risk_block:
                out_lines.append("")  # spacing after the Risk-Off line
                out_lines.append("────────────")  # separator after headline block
            continue

        # Event heading
        if line.startswith("EVENT "):
            if in_event:
                if out_lines and out_lines[-1] != "":
                    out_lines.append("")
                out_lines.append("────────────")
            in_event = True

            out_lines.append(mdv2_bold(f"🌍 {line}"))
            continue

        # Context label
        if line == "Context:":
            out_lines.append(mdv2_italic("📝CONTEXT:"))
            continue

        # Scenario details (FOCUS / RATIONALE) — must be BEFORE generic "- " bullets
        m_focus = RE_FOCUS_LINE.match(line)
        if m_focus:
            val = m_focus.group(1).strip()
            out_lines.append(f"{mdv2_italic('🎯 FOCUS:')} {mdv2_escape(val)}")
            last_was_context = False
            continue

        m_rat = RE_RATIONALE_LINE.match(line)
        if m_rat:
            val = m_rat.group(1).strip()
            out_lines.append(f"{mdv2_italic('🧠 RATIONALE:')} {mdv2_escape(val)}")
            out_lines.append("")  # breathing room after each scenario
            last_was_context = False
            continue

        # Context bullets (escape leading "-")
        if line.startswith("- "):
            out_lines.append(f"\\- {mdv2_escape(line[2:])}")
            last_was_context = True
            continue

        # Scenario headline — add blank line after context
        if line.startswith("• "):
            if last_was_context:
                out_lines.append("")  # THIS creates the visual gap
                last_was_context = False

            out_lines.append(f"{mdv2_escape('🧩')} {mdv2_bold(line[2:])}")
            continue

        # Anything else: ignore for cleanliness
        continue

    # Footer separator (avoid double blank)
    if out_lines and out_lines[-1] != "":
        out_lines.append("")
    out_lines.append("────────────")
    out_lines.append(mdv2_italic(
        "⚠️SCENARIO-BASED MARKET COMMENTARY FOR RESEARCH AND INFORMATION PURPOSES ONLY. NOT INVESTMENT ADVICE."))
    out_lines.append("────────────")

    out = "\n".join(out_lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out

