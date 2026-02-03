# daily_playbook/src/playbook/bot/build.py
from __future__ import annotations

from playbook.config import PlaybookConfig
from playbook.providers.geopolitics_headlines import fetch_daily_playbook
from playbook.render.template import render_playbook


def build_message_and_raw(cfg: PlaybookConfig) -> tuple[str, str]:
    raw = fetch_daily_playbook(cfg)
    rendered = render_playbook(raw)
    return rendered, raw


def build_message(cfg: PlaybookConfig) -> str:
    rendered, _ = build_message_and_raw(cfg)
    return rendered
