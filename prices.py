import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from db import Conn, now
from logs import log

BASE = "https://api.twelvedata.com"
# Free tier allows 8 API credits a minute; leave headroom for the health probe.
MAX_FETCH_PER_REQUEST = 6
# The health probe costs a credit too, so don't run it on every health check.
HEALTH_PROBE_EVERY = 15 * 60
TIMEOUT = 10

_health_cache: tuple[float, dict] | None = None


def _get(path: str, params: dict) -> dict:
    with urllib.request.urlopen(f"{BASE}/{path}?{urllib.parse.urlencode(params)}", timeout=TIMEOUT) as resp:
        data = json.load(resp)
    if data.get("status") == "error":
        raise RuntimeError(f"Twelve Data {data.get('code')}: {data.get('message')}")
    return data


def fetch_return(symbol: str, baseline: str, key: str) -> tuple[float, str]:
    """Price return, %, from the last close on or before `baseline` to the latest close."""
    start = (date.fromisoformat(baseline) - timedelta(days=10)).isoformat()
    data = _get("time_series", {"symbol": symbol, "interval": "1day", "start_date": start, "end_date": date.today().isoformat(), "apikey": key, "outputsize": 5000})
    series = sorted((v["datetime"][:10], float(v["close"])) for v in data["values"])
    before = [close for day, close in series if day <= baseline]
    if not before:
        raise RuntimeError(f"{symbol}: no close on or before {baseline}")
    last_day, last = series[-1]
    return round((last / before[-1] - 1) * 100, 2), last_day


def returns_for(c: Conn, tickers: set[str], baseline: str) -> tuple[dict, list[str]]:
    """Cached returns for `tickers`, refreshing stale ones from Twelve Data when a key is configured.

    Returns (returns by ticker, problems). A failed fetch keeps the cached value and stops further
    fetches for this request, so an outage costs one timeout, not one per ticker.
    """
    rows = {r["ticker"]: r for r in c.all("SELECT * FROM prices WHERE baseline = ?", (baseline,)) if r["ticker"] in tickers}
    problems = []
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        problems.append("Live prices are off: TWELVE_DATA_API_KEY is not set.")
    else:
        today = datetime.now(timezone.utc).date().isoformat()
        stale = sorted(t for t in tickers if t not in rows or rows[t]["source"] != "twelvedata" or rows[t]["fetched_at"][:10] < today)
        for ticker in stale[:MAX_FETCH_PER_REQUEST]:
            try:
                value, as_of = fetch_return(ticker, baseline, key)
            except Exception as exc:
                log("warning", "price fetch failed", ticker=ticker, error=str(exc))
                _record({"ok": False, "error": str(exc)})
                problems.append(f"Price refresh failed ({exc}); showing cached figures.")
                break
            row = {"ticker": ticker, "baseline": baseline, "low": value, "high": value, "as_of": as_of, "confidence": "high",
                   "source": "twelvedata", "sources": json.dumps([f"{BASE}/time_series?symbol={ticker}"]), "fetched_at": now()}
            c.all(
                """INSERT INTO prices (ticker, baseline, low, high, as_of, confidence, source, sources, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (ticker, baseline) DO UPDATE SET low = excluded.low, high = excluded.high, as_of = excluded.as_of,
                   confidence = excluded.confidence, source = excluded.source, sources = excluded.sources, fetched_at = excluded.fetched_at""",
                tuple(row.values()),
            )
            rows[ticker] = row
            _record({"ok": True, "last_fetch": row["fetched_at"]})
            log("info", "price fetched", ticker=ticker, value=value, as_of=as_of)
        if len(stale) > MAX_FETCH_PER_REQUEST:
            problems.append(f"{len(stale) - MAX_FETCH_PER_REQUEST} tickers still stale (rate limit); reload in a minute.")
    returns = {t: {**r, "sources": json.loads(r["sources"])} for t, r in rows.items()}
    return returns, problems


def _record(result: dict) -> None:
    global _health_cache
    _health_cache = (time.monotonic(), result)


def check() -> dict:
    """Twelve Data status: the outcome of the last real fetch, or a fresh probe if that is too old."""
    if _health_cache and time.monotonic() - _health_cache[0] < HEALTH_PROBE_EVERY:
        return _health_cache[1]
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        result = {"ok": False, "error": "TWELVE_DATA_API_KEY not set"}
    else:
        try:
            usage = _get("api_usage", {"apikey": key})
            result = {"ok": True, "usage": f"{usage.get('current_usage')}/{usage.get('plan_limit')} per minute"}
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
    _record(result)
    return result
