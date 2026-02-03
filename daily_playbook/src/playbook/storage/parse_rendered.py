from __future__ import annotations

import re
from typing import Any


RE_EVENT = re.compile(r"^🌍\s*EVENT\s+(\d+):\s*(.+)$")
RE_CONTEXT = re.compile(r"^📝CONTEXT:$")
RE_SCENARIO = re.compile(r"^🧩\s*(.+)$")
RE_FOCUS = re.compile(r"^🎯\s*FOCUS:\s*(.+)$")
RE_RATIONALE = re.compile(r"^🧠\s*RATIONALE:\s*(.+)$")


def strip_mdv2(text: str) -> str:
    """
    Convert Telegram MarkdownV2 line into plain text suitable for parsing.
    - Removes escape backslashes (\\- \\( \\) \\. etc)
    - Strips surrounding bold/italic markers *...* and _..._
    - Removes leftover * and _ that wrap tokens
    """
    if text is None:
        return ""

    x = text.strip()

    # 1) Unescape MarkdownV2 backslashes
    # (Telegram MDv2 uses backslash to escape special chars)
    x = x.replace("\\", "")

    # 2) Strip wrapping bold/italic markers repeatedly
    # e.g. "*🌍 EVENT...*" or "_📝CONTEXT:_"
    # Do it a few times to handle nested/combined cases
    for _ in range(3):
        if len(x) >= 2 and ((x[0] == "*" and x[-1] == "*") or (x[0] == "_" and x[-1] == "_")):
            x = x[1:-1].strip()

    # 3) Remove any remaining markdown markers that may be inside
    x = x.replace("*", "").replace("_", "").strip()

    return x


def parse_playbook_rendered(rendered: str) -> dict[str, Any]:
    """
    Parse the rendered playbook into:
    - events: [{event_no, title}]
    - context: [{event_no, bullet_no, text}]
    - scenarios: [{event_no, scenario_no, headline, focus, rationale}]
    """
    lines = [(ln or "").strip() for ln in (rendered or "").splitlines()]
    lines = [ln for ln in lines if ln and ln != "────────────"]

    events = []
    context = []
    scenarios = []

    cur_event_no = None
    scenario_no = 0
    in_context = False
    last_scenario_idx = None

    bullet_no = 0

    for ln in lines:
        plain = strip_mdv2(ln)

        # Skip header/footer lines
        if plain.startswith("📘 DAILY MACRO PLAYBOOK"):
            continue
        if plain.startswith("📅 "):
            continue
        if plain.startswith("Daily Macro & Trading Playbook"):
            continue
        if plain.startswith("🟢 Risk-On:") or plain.startswith("🔴 Risk-Off:"):
            continue
        if "SCENARIO-BASED MARKET COMMENTARY" in plain:
            continue

        m_ev = RE_EVENT.match(plain)
        if m_ev:
            cur_event_no = int(m_ev.group(1))
            title = m_ev.group(2).strip()
            events.append({"event_no": cur_event_no, "title": title})
            in_context = False
            bullet_no = 0
            scenario_no = 0
            last_scenario_idx = None
            continue

        if RE_CONTEXT.match(plain):
            in_context = True
            bullet_no = 0
            continue

        # Context bullets (rendered as "- x" but in MDv2 you escaped "-"; after strip it's "- ")
        if in_context and plain.startswith("- "):
            bullet_no += 1
            context.append({"event_no": cur_event_no, "bullet_no": bullet_no, "text": plain[2:].strip()})
            continue

        # Scenario headline
        m_sc = RE_SCENARIO.match(plain)
        if m_sc:
            in_context = False
            scenario_no += 1
            headline = m_sc.group(1).strip()
            scenarios.append(
                {"event_no": cur_event_no, "scenario_no": scenario_no, "headline": headline, "focus": None, "rationale": None}
            )
            last_scenario_idx = len(scenarios) - 1
            continue

        # Focus / Rationale lines attach to last scenario
        m_f = RE_FOCUS.match(plain)
        if m_f and last_scenario_idx is not None:
            scenarios[last_scenario_idx]["focus"] = m_f.group(1).strip()
            continue

        m_r = RE_RATIONALE.match(plain)
        if m_r and last_scenario_idx is not None:
            scenarios[last_scenario_idx]["rationale"] = m_r.group(1).strip()
            continue

    return {"events": events, "context": context, "scenarios": scenarios}
