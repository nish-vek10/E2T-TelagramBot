# daily_playbook/run_playbook.py
from __future__ import annotations

import sys
from pathlib import Path

# Ensure imports work when running from repo root or Heroku
THIS_DIR = Path(__file__).resolve().parent
SRC_DIR = THIS_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from playbook.bot.run import main

if __name__ == "__main__":
    raise SystemExit(main())
