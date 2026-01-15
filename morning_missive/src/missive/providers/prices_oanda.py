from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, List
import requests

@dataclass
class OandaPrice:
    instrument: str
    daily_close: Optional[float]
    daily_time: Optional[str]
    live_mid: Optional[float]

def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}

def fetch_prices(*, base_url: str, api_key: str, account_id: str, instruments: List[str]) -> Dict[str, OandaPrice]:
    out: Dict[str, OandaPrice] = {}

    # 1) Daily close (last complete candle)
    for inst in instruments:
        try:
            url = f"{base_url}/v3/instruments/{inst}/candles"
            params = {"granularity": "D", "count": "3", "price": "M"}
            r = requests.get(url, headers=_headers(api_key), params=params, timeout=20)
            r.raise_for_status()
            js = r.json()
            candles = js.get("candles", []) or []
            complete = [c for c in candles if c.get("complete") is True]
            if not complete:
                out[inst] = OandaPrice(inst, None, None, None)
                continue
            last = complete[-1]
            close = float(last["mid"]["c"])
            t = str(last.get("time", ""))
            out[inst] = OandaPrice(inst, close, t, None)
        except Exception:
            out[inst] = OandaPrice(inst, None, None, None)

    # 2) Live mid (pricing endpoint requires account)
    if account_id:
        try:
            url = f"{base_url}/v3/accounts/{account_id}/pricing"
            params = {"instruments": ",".join(instruments)}
            r = requests.get(url, headers=_headers(api_key), params=params, timeout=20)
            r.raise_for_status()
            js = r.json()
            for p in (js.get("prices", []) or []):
                inst = p.get("instrument")
                bids = p.get("bids", [])
                asks = p.get("asks", [])
                if not inst or not bids or not asks:
                    continue
                bid = float(bids[0]["price"])
                ask = float(asks[0]["price"])
                mid = (bid + ask) / 2.0
                if inst in out:
                    out[inst].live_mid = mid
                else:
                    out[inst] = OandaPrice(inst, None, None, mid)
        except Exception:
            pass

    return out
