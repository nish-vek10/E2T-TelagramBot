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
        # Always load repo-root .env (works on Windows)
        repo_root = Path(__file__).resolve().parents[
            3]  # playbook/config.py -> daily_playbook/src -> daily_playbook -> repo root? (we'll use .env search below)

        # Walk upwards until we find .env
        p = Path(__file__).resolve()
        env_path = None
        for parent in [p.parent] + list(p.parents):
            candidate = parent / ".env"
            if candidate.exists():
                env_path = candidate
                break

        if env_path is not None:
            load_dotenv(env_path, override=True)
            # TEMP DEBUG (keep for now)
            print(f"[daily_playbook] Loaded .env from: {env_path}")
            print(f"[daily_playbook] PERPLEXITY_API_KEY present? {bool(os.getenv('PERPLEXITY_API_KEY'))}")
        else:
            print("[daily_playbook] WARNING: Could not find .env by walking up folders.")

        # IMPORTANT: user asked to use MISSIVE_CHAT_ID for test now
        chat_id = _get_env("PLAYBOOK_CHAT_ID", "@e2t_MorningMissive") or "@e2t_MorningMissive"

        cfg = PlaybookConfig(
            chat_id=chat_id,
            dry_run=_get_bool("PLAYBOOK_DRY_RUN", True),
            tz=_get_env("PLAYBOOK_TZ", "Europe/London") or "Europe/London",
            post_time=_get_env("PLAYBOOK_POST_TIME", "07:30") or "07:30",
            run_once=_get_bool("PLAYBOOK_RUN_ONCE", True),
            perplexity_api_key=_get_env("PERPLEXITY_API_KEY", "") or "",
            perplexity_model=_get_env("PERPLEXITY_MODEL", "sonar") or "sonar",
        )

        # For dry-run, we still want the Perplexity key because we are fetching content
        if not cfg.perplexity_api_key:
            raise RuntimeError("Missing PERPLEXITY_API_KEY in .env (required to fetch playbook).")

        # Basic sanity check
        if ":" not in cfg.post_time:
            raise RuntimeError("PLAYBOOK_POST_TIME must be in HH:MM format (e.g., 07:30).")

        return cfg
