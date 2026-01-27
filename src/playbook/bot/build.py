# daily_playbook/src/playbook/bot/build.py
from __future__ import annotations

from playbook.config import PlaybookConfig
from playbook.providers.geopolitics_headlines import fetch_daily_playbook
from playbook.render.template import render_playbook


def build_message(cfg: PlaybookConfig) -> str:
    raw = fetch_daily_playbook(cfg)
    return render_playbook(raw)
