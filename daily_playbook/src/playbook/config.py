# daily_playbook/src/playbook/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _get_env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name)
    if val is None:
        return default
    v = val.strip()
    return v if v != "" else default


def _get_bool(name: str, default: bool = False) -> bool:
    v = _get_env(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "y", "on")


@dataclass(frozen=True)
class PlaybookConfig:
    # Telegram
    chat_id: str
    dry_run: bool

    # Schedule
    tz: str
    post_time: str  # "HH:MM"
    run_once: bool

    # Perplexity
    perplexity_api_key: str
    perplexity_model: str

    @staticmethod
    def load() -> "PlaybookConfig":

        # Load .env ONLY locally (Heroku sets DYNO env var)
        if os.getenv("DYNO"):
            print("[daily_playbook] NOTE: Running on Heroku (DYNO set) — skipping .env load.")
        else:
            # Walk upwards until we find .env (local dev only)
            p = Path(__file__).resolve()
            env_path = None
            for parent in [p.parent] + list(p.parents):
                candidate = parent / ".env"
                if candidate.exists():
                    env_path = candidate
                    break

            if env_path is not None:
                load_dotenv(env_path, override=False)
                print(f"[daily_playbook] Loaded .env from: {env_path}")
            else:
                print("[daily_playbook] NOTE: .env not found (local).")

        chat_id = _get_env("PLAYBOOK_CHAT_ID", "")
        if not chat_id:
            raise RuntimeError("Missing PLAYBOOK_CHAT_ID (required).")

        cfg = PlaybookConfig(
            chat_id=chat_id,
            dry_run=_get_bool("PLAYBOOK_DRY_RUN", False),
            tz=_get_env("PLAYBOOK_TZ", "Europe/London") or "Europe/London",
            post_time=_get_env("PLAYBOOK_POST_TIME", "07:00") or "07:00",
            run_once=_get_bool("PLAYBOOK_RUN_ONCE", False),
            perplexity_api_key=_get_env("PERPLEXITY_API_KEY", "") or "",
            perplexity_model=_get_env("PERPLEXITY_MODEL", "sonar") or "sonar",
        )

        if not cfg.perplexity_api_key:
            raise RuntimeError("Missing PERPLEXITY_API_KEY (required).")

        if ":" not in cfg.post_time:
            raise RuntimeError("PLAYBOOK_POST_TIME must be HH:MM (e.g., 07:00).")

        return cfg
