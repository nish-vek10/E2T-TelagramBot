# morning_missive/run_missive.py

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from missive.bot.run import main  # noqa

if __name__ == "__main__":
    main()
