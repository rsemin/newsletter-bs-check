import html
import json
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text())


def basket(tickers: list[str], returns: dict) -> dict | None:
    rows = [returns[t] for t in tickers if t in returns]
    if len(rows) != len(tickers):
        return None
    return {
        "low": sum(r["low"] for r in rows) / len(rows),
        "high": sum(r["high"] for r in rows) / len(rows),
        "confidence": min((r["confidence"] for r in rows), key=["low", "medium", "high"].index),
    }


def verdict(low: float, high: float) -> str:
    if low > 0:
        return "On track"
    if high < 0:
        return "Off track"
    return "Too close to call"


def score(rec: dict, returns: dict) -> dict:
    mine = basket(rec["track"], returns)
    bench = rec["benchmark"]
    ref = {"low": bench["target"], "high": bench["target"]} if "target" in bench else basket([bench["ticker"]], returns)
    if not mine or not ref:
        missing = [t for t in rec["track"] + [bench.get("ticker")] if t and t not in returns]
        return {**rec, "status": "No data", "missing": missing}
    excess_low, excess_high = mine["low"] - ref["high"], mine["high"] - ref["low"]
    return {
        **rec,
        "ret": mine,
        "ref": ref,
        "excess_low": excess_low,
        "excess_high": excess_high,
        "status": verdict(excess_low, excess_high),
    }


def span(low: float, high: float) -> str:
    return f"{low:+.1f}%" if abs(high - low) < 0.05 else f"{low:+.1f} to {high:+.1f}%"


def bench_label(rec: dict) -> str:
    b = rec["benchmark"]
    return f"target {b['target']:+.0f}%" if "target" in b else b["ticker"]


def table(results: list[dict]) -> str:
    lines = ["| Call | Who | Tracked | Return | vs | Excess | Verdict |", "|---|---|---|---:|---|---:|---|"]
    for r in results:
        if r["status"] == "No data":
            lines.append(f"| {r['call']} | {r['who']} | {', '.join(r['track'])} | – | {bench_label(r)} | – | No data ({', '.join(r['missing'])}) |")
            continue
        lines.append(
            f"| {r['call']} | {r['who']} | {', '.join(r['track'])} | {span(r['ret']['low'], r['ret']['high'])} | {bench_label(r)} | "
            f"{span(r['excess_low'], r['excess_high'])} | {r['status']} |"
        )
    return "\n".join(lines)


STATUS_CLASS = {"On track": "good", "Off track": "bad", "Too close to call": "mid", "No data": "none"}

CSS = """
:root{--bg:#fafaf8;--fg:#1c1c1a;--muted:#6b6b66;--line:#e4e3de;--card:#fff;--good:#1f7a4d;--bad:#b3261e;--mid:#8a6d00;--none:#77756f;--bar:#d9d7d0}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--fg:#ecebe6;--muted:#a09f99;--line:#2c2c29;--card:#1f1f1d;--good:#5cc28d;--bad:#f2867d;--mid:#e0c25a;--none:#a09f99;--bar:#3a3a36}}
:root[data-theme="dark"]{--bg:#161615;--fg:#ecebe6;--muted:#a09f99;--line:#2c2c29;--card:#1f1f1d;--good:#5cc28d;--bad:#f2867d;--mid:#e0c25a;--none:#a09f99;--bar:#3a3a36}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:960px;margin:0 auto;padding:32px 16px 64px}h1{font-size:24px;margin:0 0 4px}p.sub{color:var(--muted);margin:0 0 24px}
.summary{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px}.pill{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.pill b{font-size:20px;display:block}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:12px}
.head{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline}.call{font-weight:600}.who{color:var(--muted);font-size:13px}
.status{font-weight:600;font-size:13px;white-space:nowrap}.good{color:var(--good)}.bad{color:var(--bad)}.mid{color:var(--mid)}.none{color:var(--none)}
.nums{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin:12px 0;font-size:13px}.nums span{color:var(--muted);display:block}
.track{position:relative;height:10px;background:var(--bar);border-radius:5px;margin:4px 0 12px}.zero{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--fg)}
.fill{position:absolute;top:0;bottom:0;border-radius:5px}.thesis,.why{font-size:14px;margin:6px 0}.why{border-left:3px solid var(--line);padding-left:10px}
.quote{color:var(--muted);font-size:13px;font-style:italic}.foot{color:var(--muted);font-size:12px;margin-top:32px}.foot a{color:inherit}
"""


def bar(r: dict, scale: float) -> str:
    if r["status"] == "No data":
        return ""
    def pos(v: float) -> float:
        return 50 + max(-50, min(50, v / scale * 50))
    left, right = sorted((pos(r["excess_low"]), pos(r["excess_high"])))
    lo, hi = min(left, 50), max(right, 50)
    colour = f"var(--{STATUS_CLASS[r['status']]})"
    return (
        f'<div class="track" title="Excess return vs benchmark"><div class="fill" style="left:{lo:.1f}%;width:{max(hi - lo, 0.8):.1f}%;background:{colour};opacity:.85"></div>'
        f'<div class="zero" style="left:50%"></div></div>'
    )


def card(r: dict, why: str, scale: float) -> str:
    e = html.escape
    if r["status"] == "No data":
        nums = f"<div><span>Missing price data</span>{e(', '.join(r['missing']))}</div>"
    else:
        nums = (
            f"<div><span>Tracked ({e(', '.join(r['track']))})</span>{span(r['ret']['low'], r['ret']['high'])}</div>"
            f"<div><span>Benchmark ({e(bench_label(r))})</span>{span(r['ref']['low'], r['ref']['high'])}</div>"
            f"<div><span>Excess</span>{span(r['excess_low'], r['excess_high'])}</div>"
            f"<div><span>Data confidence</span>{e(r['ret']['confidence'])}</div>"
        )
    return (
        f'<div class="card"><div class="head"><div><div class="call">{e(r["call"])}</div><div class="who">{e(r["who"])}</div></div>'
        f'<div class="status {STATUS_CLASS[r["status"]]}">{e(r["status"])}</div></div>'
        f'<div class="nums">{nums}</div>{bar(r, scale)}'
        f'<p class="thesis"><b>Thesis:</b> {e(r["thesis"])}</p><p class="quote">«{e(r["quote"])}»</p>'
        f'<p class="why"><b>Why (hypothesis):</b> {e(why)}</p></div>'
    )


def page(meta: dict, results: list[dict], explanations: dict, returns: dict) -> str:
    e = html.escape
    counts = {s: sum(r["status"] == s for r in results) for s in STATUS_CLASS}
    scale = max((max(abs(r["excess_low"]), abs(r["excess_high"])) for r in results if r["status"] != "No data"), default=10)
    pills = "".join(f'<div class="pill"><b class="{STATUS_CLASS[s]}">{n}</b>{e(s)}</div>' for s, n in counts.items() if n)
    cards = "".join(card(r, explanations.get(r["id"], "Not yet analysed."), scale) for r in results)
    sources = "".join(
        f"<li>{t}: {span(v['low'], v['high'])} as of {v['as_of']} ({v['confidence']}): "
        + ", ".join(f'<a href="{e(u)}">{e(u.split("/")[2])}</a>' for u in v["sources"]) + "</li>"
        for t, v in returns["tickers"].items()
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recommendation Tracker</title><style>{CSS}</style></head><body><main>
<h1>Are these calls working?</h1>
<p class="sub">{e(meta['publisher'])} · “{e(meta['title'])}” · published {e(meta['published'])} · scored on {e(returns['basis'])}</p>
<div class="summary">{pills}</div>{cards}
<div class="foot"><p>Excess = tracked return minus benchmark, shown as a range where sources disagree. A verdict is given only when the whole range is on one side of zero.
Returns are measured from the {e(meta.get('baseline', '2025-12-31'))} close. Verdicts are interim until the call's horizon ends.</p>
<p>{e(returns['note'])}</p><ul>{sources}</ul></div></main></body></html>"""


def main() -> None:
    recs = load("recommendations.json")
    returns = load("returns.json")
    explanations = load("explanations.json") if (DATA / "explanations.json").exists() else {}
    results = [score(r, returns["tickers"]) for r in recs["recommendations"]]
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    (HERE / "out" / "report.html").write_text(page(recs["source"], results, explanations, returns))
    print(table(results))


if __name__ == "__main__":
    main()
