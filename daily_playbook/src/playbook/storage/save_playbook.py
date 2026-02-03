from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from playbook.storage.parse_rendered import parse_playbook_rendered


def save_playbook_to_supabase(
    *,
    supabase,
    tz: str,
    post_time: str,
    telegram_chat_id: str,
    rendered_text: str,
    raw_text: str,
    posted_to_telegram: bool,
) -> str:
    """
    Upserts today's playbook by London date, clears + replaces children.
    Returns playbook_id.
    """
    now_local = datetime.now(ZoneInfo(tz))
    post_date = now_local.date().isoformat()

    master = {
        "post_date": post_date,
        "tz": tz,
        "asof_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "post_time": post_time,
        "telegram_chat_id": str(telegram_chat_id),
        "posted_to_telegram": bool(posted_to_telegram),
        "rendered_text": rendered_text,
        "raw_text": raw_text,
    }

    up = supabase.table("playbooks").upsert(master, on_conflict="post_date").execute()
    playbook_id = up.data[0]["id"]

    # clear children
    supabase.table("playbook_events").delete().eq("playbook_id", playbook_id).execute()
    supabase.table("playbook_event_context").delete().eq("playbook_id", playbook_id).execute()
    supabase.table("playbook_event_scenarios").delete().eq("playbook_id", playbook_id).execute()

    parsed = parse_playbook_rendered(rendered_text)

    # insert events
    ev_rows = [{"playbook_id": playbook_id, "event_no": e["event_no"], "title": e["title"]} for e in parsed["events"]]
    if ev_rows:
        supabase.table("playbook_events").insert(ev_rows).execute()

    # insert context
    ctx_rows = [
        {"playbook_id": playbook_id, "event_no": c["event_no"], "bullet_no": c["bullet_no"], "text": c["text"]}
        for c in parsed["context"]
        if c.get("event_no") is not None
    ]
    if ctx_rows:
        supabase.table("playbook_event_context").insert(ctx_rows).execute()

    # insert scenarios
    sc_rows = [
        {
            "playbook_id": playbook_id,
            "event_no": s["event_no"],
            "scenario_no": s["scenario_no"],
            "headline": s["headline"],
            "focus": s.get("focus"),
            "rationale": s.get("rationale"),
        }
        for s in parsed["scenarios"]
        if s.get("event_no") is not None
    ]
    if sc_rows:
        supabase.table("playbook_event_scenarios").insert(sc_rows).execute()

    return str(playbook_id)
