# morning_missive/src/missive/config.py

from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

def _repo_root() -> Path:
    # .../E2T-TelegramBot/morning_missive/src/missive/config.py -> parents[3] = E2T-TelegramBot
    return Path(__file__).resolve().parents[3]

def _load_root_env() -> None:
    env_path = _repo_root() / ".env"
    if env_path.exists():
        load_dotenv(env_path)

def _s(key: str, default: str = "") -> str:
    return str(os.getenv(key, default)).strip()

def _i(key: str, default: int) -> int:
    v = os.getenv(key)
    return int(v) if v and v.strip() else default

def _b(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y")

_load_root_env()

@dataclass(frozen=True)
class Settings:
    # Telegram
    MISSIVE_BOT_TOKEN: str = _s("MISSIVE_BOT_TOKEN")
    MISSIVE_CHAT_ID: str = _s("MISSIVE_CHAT_ID")
    MISSIVE_THREAD_ID: int = _i("MISSIVE_THREAD_ID", 0)  # 0 = no topic/thread
    MISSIVE_DRY_RUN: bool = _b("MISSIVE_DRY_RUN", True)

    # Schedule
    TZ: str = _s("MISSIVE_TZ", "Europe/London")
    POST_HOUR: int = _i("MISSIVE_POST_HOUR", 7)
    POST_MINUTE: int = _i("MISSIVE_POST_MINUTE", 30)

    # OANDA
    OANDA_ENV: str = _s("OANDA_ENV", "practice")  # practice/live
    OANDA_API_KEY: str = _s("OANDA_API_KEY")
    OANDA_ACCOUNT_ID: str = _s("OANDA_ACCOUNT_ID")
    INSTRUMENTS: str = _s("MISSIVE_INSTRUMENTS", "SPX500_USD,NAS100_USD,XAU_USD,WTICO_USD,BTC_USD,ETH_USD")

    # Headlines (GDELT + whitelist)
    HEADLINES_LOOKBACK_HOURS: int = _i("MISSIVE_HEADLINES_LOOKBACK_HOURS", 18)
    HEADLINES_MAX: int = _i("MISSIVE_HEADLINES_MAX", 10)
    HEADLINES_QUERY: str = _s(
        "MISSIVE_HEADLINES_QUERY",
        '(Federal Reserve OR CPI OR inflation OR Treasury OR geopolitics OR'
                ' oil OR OPEC OR '
                'Ukraine OR China OR sanctions OR "central bank")',
    )
    HEADLINE_DOMAINS: str = _s("MISSIVE_HEADLINE_DOMAINS", "reuters.com,bloomberg.com,cnbc.com,ft.com,wsj.com")


    @property
    def oanda_base_url(self) -> str:
        return "https://api-fxtrade.oanda.com" if self.OANDA_ENV.lower() == "live" else "https://api-fxpractice.oanda.com"

    @property
    def instruments_list(self) -> list[str]:
        return [x.strip() for x in self.INSTRUMENTS.split(",") if x.strip()]

    @property
    def headline_domains_list(self) -> list[str]:
        return [x.strip().lower() for x in self.HEADLINE_DOMAINS.split(",") if x.strip()]

