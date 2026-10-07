import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
BASE = "https://api.twelvedata.com/time_series"
START = "2025-12-24"
BASELINE = "2025-12-31"


def load_env() -> None:
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def closes(symbol: str, key: str) -> list[tuple[str, float]]:
    query = urllib.parse.urlencode({"symbol": symbol, "interval": "1day", "start_date": START, "end_date": date.today().isoformat(), "apikey": key, "outputsize": 5000})
    with urllib.request.urlopen(f"{BASE}?{query}", timeout=30) as resp:
        data = json.load(resp)
    if data.get("status") != "ok":
        raise RuntimeError(f"{symbol}: {data.get('message', data)}")
    return sorted((v["datetime"][:10], float(v["close"])) for v in data["values"])


def ytd(series: list[tuple[str, float]]) -> tuple[float, str]:
    base = [c for d, c in series if d <= BASELINE][-1]
    last_date, last = series[-1]
    return round((last / base - 1) * 100, 2), last_date


def main() -> None:
    load_env()
    key = os.environ.get("TWELVE_DATA_API_KEY") or sys.exit("Set TWELVE_DATA_API_KEY in .env")
    recs = json.loads((HERE / "data" / "recommendations.json").read_text())["recommendations"]
    symbols = sorted({t for r in recs for t in r["track"]} | {r["benchmark"]["ticker"] for r in recs if "ticker" in r["benchmark"]})
    tickers = {}
    for i, symbol in enumerate(symbols):
        if i and i % 8 == 0:
            time.sleep(61)
        value, as_of = ytd(closes(symbol, key))
        tickers[symbol] = {"low": value, "high": value, "as_of": as_of, "confidence": "high", "sources": [f"{BASE}?symbol={symbol}"]}
        print(f"{symbol}: {value:+.2f}% as of {as_of}")
    out = {"basis": "2026 year-to-date price return, %, from 31 Dec 2025 close", "method": "twelvedata", "note": "Daily closes from Twelve Data.", "tickers": tickers}
    (HERE / "data" / "returns.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
