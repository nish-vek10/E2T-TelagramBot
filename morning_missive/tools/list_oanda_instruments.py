import os
import requests
from dotenv import load_dotenv
from pathlib import Path

# load root .env
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

BASE = "https://api-fxtrade.oanda.com" if os.getenv("OANDA_ENV","practice").lower()=="live" else "https://api-fxpractice.oanda.com"
API_KEY = os.getenv("OANDA_API_KEY","").strip()
ACC = os.getenv("OANDA_ACCOUNT_ID","").strip()

r = requests.get(
    f"{BASE}/v3/accounts/{ACC}/instruments",
    headers={"Authorization": f"Bearer {API_KEY}"},
    timeout=30
)
r.raise_for_status()
inst = r.json().get("instruments", [])

# print likely index CFDs
needles = ["US500", "SPX", "NAS", "XAU", "WTI", "BTC", "ETH", "DXY"]
for x in inst:
    name = x.get("name","")
    if any(n in name for n in needles):
        print(name)
