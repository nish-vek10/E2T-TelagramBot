from __future__ import annotations

import yaml
from pathlib import Path

from missive.config import Settings
from missive.utils.log import get_logger

from missive.providers.prices_oanda import fetch_prices
from missive.providers.headlines_gdelt import fetch_headlines
from missive.render.template import build_message

log = get_logger("missive_build")

# morning_missive/ (this file is morning_missive/src/missive/bot/build.py)
ROOT = Path(__file__).resolve().parents[3]  # -> morning_missive/
DATA_DIR = ROOT / "app_data"


def _load_focus_events() -> dict:
    """
    Optional YAML: morning_missive/app_data/events.yaml
      eu: ["09:30 — UK: CPI", ...]
      us: ["13:30 — US: CPI", ...]
      asia: ["00:30 — AUS: CPI", ...]
    """
    path = DATA_DIR / "events.yaml"
    if not path.exists():
        return {"eu": [], "us": [], "asia": []}

    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "eu": [str(x) for x in (d.get("eu") or [])],
        "us": [str(x) for x in (d.get("us") or [])],
        "asia": [str(x) for x in (d.get("asia") or [])],
    }


def _load_bond_supply() -> list[str]:
    """
    Optional YAML: morning_missive/app_data/bonds.yaml
      items:
        - "UK DMO: ..."
        - "UST: ..."
    """
    path = DATA_DIR / "bonds.yaml"
    if not path.exists():
        return []

    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = d.get("items") if isinstance(d, dict) else d
    if not items:
        return []
    return [str(x) for x in items]


def build_missive_text() -> str:
    """
    Builds the final Morning Missive message string.
    Safe to call from inside app/bot.py JobQueue or /missive_test.
    """
    s = Settings()

    prices = fetch_prices(
        base_url=s.oanda_base_url,
        api_key=s.OANDA_API_KEY,
        account_id=s.OANDA_ACCOUNT_ID,
        instruments=s.instruments_list,
    )

    headlines = fetch_headlines(
        query=s.HEADLINES_QUERY,
        tz=s.TZ,
        lookback_hours=s.HEADLINES_LOOKBACK_HOURS,
        limit=s.HEADLINES_MAX,
        whitelist_domains=s.headline_domains_list,
    )

    focus_events = _load_focus_events()
    bonds = _load_bond_supply()

    return build_message(
        tz=s.TZ,
        prices=prices,
        headlines=headlines,
        focus_events=focus_events,
        bond_supply=bonds,
    )
