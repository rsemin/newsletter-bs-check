# rec-tracker: progress so far

_Last updated: 10 Oct 2026_

## Goal

Take investment recommendations from newsletters and research PDFs, turn each into a call that can be tested, track the instruments against real market data, and explain why each call is or isn't working. In the long run: one view across every recommendation, showing whether the source's calls hold up.

## What exists today

A working pipeline for **one newsletter**: Bell.Инвестиции, 26 Dec 2025, "Во что крупнейшие инвестбанки рекомендуют инвестировать в 2026 году".

```
newsletter ─► recommendations.json ─► returns.json ─► score.py ─► out/report.html
```

| Step | Status | How it's done now |
|---|---|---|
| Ingest | Manual | The `.eml` was uploaded into the chat |
| Extract calls | Done for 1 issue | Claude in-session, saved to `data/recommendations.json` (10 calls: who, call, thesis, original quote, tracked ETFs, benchmark) |
| Prices | Approximate | 2026 year-to-date total returns from web search, saved as low/high ranges with date, confidence and sources in `data/returns.json` |
| Score | Done | `score.py`: return against the benchmark; a verdict only when the whole range is on one side of zero |
| Explain | Done for 1 issue | Hypotheses written by Claude in-session from the cited facts, in `data/explanations.json` |
| View | Done | `out/report.html`: one card per call |

## First result (to about 6 Oct 2026)

- **On track (3):** S&P 500 +11% consensus (SPY +15.1%), Goldman Sachs stocks over corporate credit, staying exposed to AI (QQQ about +24%).
- **Too close to call (2):** small caps, the broad sector rotation (only energy carries it).
- **Off track (4):** UBS healthcare, UBS utilities (about −4.5%, the worst call), UBS banks, HSBC utilities/financials/industrials.
- **No data (1):** PIMCO value over growth.
- **Takeaway:** the 2026 "broaden away from tech" consensus has mostly failed so far; staying with tech and AI worked.

## Known limitations

- Market-data hosts are blocked in the build environment, so prices come from web search. Sources often disagree; utilities and financials are low confidence.
- Returns are measured from 31 Dec 2025, not the publication date (26 Dec), and the horizon is all of 2026, so these are interim verdicts.
- The ETF stand-ins are judgement calls; the newsletter names sectors, not tickers.
- Extraction and explanations were done by Claude in the chat, not by an automated API call.
- `fetch_twelvedata.py` has only been checked offline: the return calculation (on made-up prices) and the missing-key error. It has never called the real API.

## Decisions made

- Python, standard library only for now.
- Twelve Data is the price provider (TradingView has no public data API).
- Gmail ingestion is parked; work from files dropped in by hand.
- Start with one newsletter end to end, then scale.

## Source material available

- Four emails in Gmail from `unistatinc@gmail.com` ("The Bell-1" to "The Bell-4", 9 Sep 2026), each holding about 20 forwarded Bell newsletters as `.eml` attachments, covering roughly Dec 2025 to Aug 2026.

## Next steps

1. Move to its own repo (see the transfer plan below).
2. Add a Twelve Data key, allow `api.twelvedata.com`, and run `fetch_twelvedata.py` for exact returns.
3. Add price charts and the worst fall along the way, from daily closes.
4. Automate extraction and explanations with the Claude API (structured output per newsletter).
5. Run the remaining newsletters through the pipeline; then add Gmail ingestion.

## Transfer plan

1. Create an empty private repo (e.g. `rsemin/rec-tracker`) and give the Claude GitHub App access.
2. `git subtree split --prefix rec-tracker -b rec-tracker-export`, then push that branch to the new repo's `main`.
3. Keep raw newsletters out of git (personal unsubscribe links, paid content); commit only the extracted data.
4. Set `TWELVE_DATA_API_KEY` and `ANTHROPIC_API_KEY` as environment secrets, and allow `api.twelvedata.com`.
5. Remove `rec-tracker/` from `claude-experiment`.
