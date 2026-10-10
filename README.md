# rec-tracker

Checks whether investment-bank recommendations from a newsletter are working.

```
newsletter (.eml) ─► recommendations.json ─► returns.json ─► score.py ─► out/report.html
                     (LLM extraction:          (Twelve Data, or      (excess return vs
                      call, thesis, quote,      sourced web figures)   benchmark, verdict,
                      tracked ETFs, benchmark)                         "why" hypothesis)
```

## Service

A small web service that stores newsletter calls and scores them against live Twelve Data prices.

| Path | What it does |
|---|---|
| `GET /` | Lists newsletters |
| `GET /newsletters/<id>` (`.json`) | Live report for one newsletter |
| `POST /newsletters` | Adds a newsletter and its calls (JSON). Repeats return the existing one (200, not 201) |
| `GET /health` | `ok` / `degraded` (prices unavailable) / `down` (database unreachable, 503). Includes the deployed commit |

```bash
python3 app.py                   # local, SQLite at data/local.db, http://localhost:8000
python3 -m unittest -v           # tests; set DATABASE_URL to run them against Postgres
```

Every request logs one JSON line with a `request_id`, which is also returned in the `X-Request-Id` header.

**Render settings:** Python web service; build `pip install -r requirements.txt`; start `python app.py`;
health check path `/health`; env vars `DATABASE_URL` (internal URL of a Render Postgres) and `TWELVE_DATA_API_KEY`;
auto-deploy "After CI checks pass".

## Batch report (original)

```bash
python3 score.py                 # table to stdout, writes out/report.html and out/results.json
cp .env.example .env             # add TWELVE_DATA_API_KEY
python3 fetch_twelvedata.py      # replaces data/returns.json with exact daily-close returns
python3 score.py
```

## Current state (first example)

- Source: Bell.Инвестиции, 26 Dec 2025, "Во что крупнейшие инвестбанки рекомендуют инвестировать в 2026 году".
- `data/recommendations.json`: 10 calls extracted by Claude in-session. The ETF proxies are judgement calls; edit them freely.
- `data/returns.json`: 2026 year-to-date total returns gathered via web search, because market-data hosts are blocked in the build environment. Each entry has a low/high range, an as-of date, a confidence level and its sources.
- `data/explanations.json`: short "why" hypotheses written by Claude in-session from the sourced facts only.
- A verdict is given only when the whole excess-return range is on one side of zero.

## Next

- Automate extraction with the Claude API (one call per newsletter, structured output).
- Run `fetch_twelvedata.py` for exact numbers and daily paths, then add charts and max drawdown.
- Source IWD/IWF to score the PIMCO value call.
