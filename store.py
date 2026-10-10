import hashlib
import json
import re
from datetime import date
from pathlib import Path

import prices
import score
from db import Conn, connect, now
from logs import log

DATA = Path(__file__).parent / "data"
TICKER = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")


class Invalid(ValueError):
    """The request body is wrong; the message is safe to show the client."""


def _text(obj: dict, field: str, where: str, required: bool = True, limit: int = 2000) -> str:
    value = obj.get(field, "")
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise Invalid(f"{where}.{field}: expected a non-empty string up to {limit} characters" if required else f"{where}.{field}: expected a string")
    return value.strip()


def _date(obj: dict, field: str, where: str) -> str:
    value = _text(obj, field, where)
    try:
        date.fromisoformat(value)
    except ValueError:
        raise Invalid(f"{where}.{field}: expected YYYY-MM-DD, got {value!r}") from None
    return value


def validate(body) -> dict:
    if not isinstance(body, dict):
        raise Invalid("body: expected a JSON object")
    nl = {
        "publisher": _text(body, "publisher", "body", limit=200),
        "title": _text(body, "title", "body", limit=500),
        "published": _date(body, "published", "body"),
        "message_id": _text(body, "message_id", "body", required=False, limit=500),
    }
    nl["baseline"] = _date(body, "baseline", "body") if body.get("baseline") else nl["published"]
    calls = body.get("calls")
    if not isinstance(calls, list) or not 1 <= len(calls) <= 50:
        raise Invalid("body.calls: expected a list of 1 to 50 calls")
    nl["calls"] = []
    for i, raw in enumerate(calls):
        where = f"calls[{i}]"
        if not isinstance(raw, dict):
            raise Invalid(f"{where}: expected an object")
        track = raw.get("track")
        if not isinstance(track, list) or not 1 <= len(track) <= 10 or not all(isinstance(t, str) and TICKER.match(t) for t in track):
            raise Invalid(f"{where}.track: expected 1 to 10 tickers like \"SPY\"")
        bench = raw.get("benchmark")
        if isinstance(bench, dict) and isinstance(bench.get("ticker"), str) and TICKER.match(bench["ticker"]):
            bench = {"ticker": bench["ticker"]}
        elif isinstance(bench, dict) and isinstance(bench.get("target"), (int, float)) and not isinstance(bench["target"], bool):
            bench = {"target": float(bench["target"])}
        else:
            raise Invalid(f"{where}.benchmark: expected {{\"ticker\": \"SPY\"}} or {{\"target\": 11.0}}")
        nl["calls"].append({
            "id": _text(raw, "id", where, limit=100) if raw.get("id") else str(i + 1),
            "who": _text(raw, "who", where, limit=300),
            "call": _text(raw, "call", where, limit=500),
            "thesis": _text(raw, "thesis", where, required=False),
            "quote": _text(raw, "quote", where, required=False),
            "explanation": _text(raw, "explanation", where, required=False) or None,
            "track": track,
            "benchmark": bench,
        })
    if len({c["id"] for c in nl["calls"]}) != len(nl["calls"]):
        raise Invalid("calls: ids must be unique within a newsletter")
    return nl


def natural_key(nl: dict) -> str:
    """What makes two submissions 'the same newsletter': the email Message-ID, else publisher + date + title."""
    return nl["message_id"] or f"{nl['publisher']}|{nl['published']}|{nl['title']}"


def add_newsletter(nl: dict) -> tuple[str, bool]:
    """Insert a validated newsletter and its calls. Idempotent: a repeat returns (existing id, False)."""
    key = natural_key(nl)
    nid = hashlib.sha256(key.encode()).hexdigest()[:10]
    with connect() as c:
        inserted = c.one(
            """INSERT INTO newsletters (id, natural_key, publisher, title, published, baseline, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (nid, key, nl["publisher"], nl["title"], nl["published"], nl["baseline"], now()),
        )
        if not inserted:
            existing = c.one("SELECT id FROM newsletters WHERE natural_key = ?", (key,))
            log("info", "duplicate newsletter ignored", newsletter_id=existing["id"])
            return existing["id"], False
        for pos, call in enumerate(nl["calls"]):
            c.all(
                """INSERT INTO calls (newsletter_id, call_id, position, who, summary, thesis, quote, track, benchmark, explanation)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (nid, call["id"], pos, call["who"], call["call"], call["thesis"], call["quote"], json.dumps(call["track"]), json.dumps(call["benchmark"]), call["explanation"]),
            )
    log("info", "newsletter added", newsletter_id=nid, calls=len(nl["calls"]))
    return nid, True


def list_newsletters() -> list[dict]:
    with connect() as c:
        return c.all(
            """SELECT n.id, n.publisher, n.title, n.published, COUNT(c.call_id) AS calls
               FROM newsletters n LEFT JOIN calls c ON c.newsletter_id = n.id
               GROUP BY n.id, n.publisher, n.title, n.published ORDER BY n.published DESC"""
        )


def report(nid: str) -> dict | None:
    """Score every call in a newsletter against current returns."""
    with connect() as c:
        nl = c.one("SELECT * FROM newsletters WHERE id = ?", (nid,))
        if not nl:
            return None
        calls = [
            {"id": r["call_id"], "who": r["who"], "call": r["summary"], "thesis": r["thesis"], "quote": r["quote"],
             "track": json.loads(r["track"]), "benchmark": json.loads(r["benchmark"]), "explanation": r["explanation"]}
            for r in c.all("SELECT * FROM calls WHERE newsletter_id = ? ORDER BY position", (nid,))
        ]
        tickers = {t for call in calls for t in call["track"]} | {call["benchmark"]["ticker"] for call in calls if "ticker" in call["benchmark"]}
        returns, problems = prices.returns_for(c, tickers, nl["baseline"])
    return {
        "newsletter": nl,
        "results": [score.score(call, returns) for call in calls],
        "explanations": {call["id"]: call["explanation"] for call in calls if call["explanation"]},
        "returns": returns,
        "problems": problems,
    }


def seed() -> None:
    """Load the hand-built first newsletter. Safe on every start because add_newsletter is idempotent."""
    recs = json.loads((DATA / "recommendations.json").read_text())
    explanations = json.loads((DATA / "explanations.json").read_text())
    src = recs["source"]
    nid, created = add_newsletter(validate({
        "publisher": src["publisher"], "title": src["title"], "published": src["published"],
        # The original analysis measured from the 31 Dec 2025 close, three trading days after publication.
        "baseline": "2025-12-31",
        "calls": [{**r, "explanation": explanations.get(r["id"], "")} for r in recs["recommendations"]],
    }))
    web = json.loads((DATA / "returns.json").read_text())
    with connect() as c:
        for ticker, v in web["tickers"].items():
            c.all(
                """INSERT INTO prices (ticker, baseline, low, high, as_of, confidence, source, sources, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (ticker, baseline) DO NOTHING""",
                (ticker, "2025-12-31", v["low"], v["high"], v["as_of"], v["confidence"], "web-search", json.dumps(v["sources"]), "seed"),
            )
    if created:
        log("info", "seeded first newsletter", newsletter_id=nid)
