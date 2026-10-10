import html
import json
import os
import re
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import db
import prices
import score
import store
from fetch_twelvedata import load_env
from logs import log, request_id

VERSION = os.environ.get("RENDER_GIT_COMMIT", "local")[:7]
MAX_BODY = 1_000_000
NEWSLETTER = re.compile(r"^/newsletters/([0-9a-f]{10})(\.json)?$")


def health() -> tuple[int, dict]:
    """503 only when the database is down: the app can't serve anything without it.
    A Twelve Data outage degrades the page (cached prices) but the app is still up."""
    checks = {}
    start = time.monotonic()
    try:
        with db.connect() as c:
            c.all("SELECT 1")
        checks["database"] = {"ok": True, "ms": round((time.monotonic() - start) * 1000)}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": str(exc)}
    checks["twelvedata"] = prices.check()
    status = "down" if not checks["database"]["ok"] else "ok" if checks["twelvedata"]["ok"] else "degraded"
    return (503 if status == "down" else 200), {"status": status, "version": VERSION, "checks": checks}


def index_page(newsletters: list[dict]) -> str:
    e = html.escape
    rows = "".join(
        f'<div class="card"><div class="call"><a href="/newsletters/{n["id"]}">{e(n["title"])}</a></div>'
        f'<div class="who">{e(n["publisher"])} · {e(n["published"])} · {n["calls"]} calls</div></div>'
        for n in newsletters
    ) or "<p>No newsletters yet. POST one to /newsletters.</p>"
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Recommendation Tracker</title><style>{score.CSS}</style></head><body><main><h1>Recommendation Tracker</h1>'
            f'<p class="sub">Newsletter investment calls, scored against live market data.</p>{rows}'
            f'<div class="foot">version {e(VERSION)} · <a href="/health">health</a></div></main></body></html>')


def report_page(r: dict) -> str:
    nl = r["newsletter"]
    returns = {
        "basis": f"return from the {nl['baseline']} close, %",
        "note": " ".join(r["problems"]) or "Twelve Data figures are price returns; web-search figures are total returns.",
        "tickers": r["returns"],
    }
    return score.page(nl, r["results"], r["explanations"], returns)


class Handler(BaseHTTPRequestHandler):
    server_version = "rec-tracker"

    def log_message(self, *args) -> None:
        pass  # replaced by one JSON line per request in handle_request

    def do_GET(self) -> None:
        self.handle_request()

    def do_POST(self) -> None:
        self.handle_request()

    def handle_request(self) -> None:
        rid = self.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        request_id.set(rid)
        self.status, start = 500, time.monotonic()
        try:
            self.route(urlsplit(self.path).path)
        except store.Invalid as exc:
            self.send_json(400, {"error": str(exc), "request_id": rid})
        except Exception:
            log("error", "unhandled exception", error=traceback.format_exc())
            self.send_json(500, {"error": "internal error", "request_id": rid})
        finally:
            log("info", "request", method=self.command, path=self.path, status=self.status, ms=round((time.monotonic() - start) * 1000))

    def route(self, path: str) -> None:
        if self.command == "POST":
            if path != "/newsletters":
                return self.send_json(404, {"error": "not found"})
            nid, created = store.add_newsletter(store.validate(self.read_json()))
            return self.send_json(201 if created else 200, {"id": nid, "created": created, "url": f"/newsletters/{nid}"})
        if path == "/health":
            return self.send_json(*health())
        if path == "/":
            return self.send_html(200, index_page(store.list_newsletters()))
        if m := NEWSLETTER.match(path):
            r = store.report(m.group(1))
            if not r:
                return self.send_json(404, {"error": "newsletter not found"})
            if m.group(2):
                return self.send_json(200, {k: r[k] for k in ("newsletter", "results", "problems")})
            return self.send_html(200, report_page(r))
        self.send_json(404, {"error": "not found"})

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise store.Invalid(f"body: larger than {MAX_BODY} bytes")
        try:
            return json.loads(self.rfile.read(length) or b"null")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise store.Invalid(f"body: not valid JSON ({exc})") from None

    def send_json(self, status: int, body: dict) -> None:
        self.send(status, "application/json", json.dumps(body, ensure_ascii=False, default=str).encode())

    def send_html(self, status: int, body: str) -> None:
        self.send(status, "text/html; charset=utf-8", body.encode())

    def send(self, status: int, content_type: str, body: bytes) -> None:
        self.status = status
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-Id", request_id.get())
        self.end_headers()
        self.wfile.write(body)


def make_server(port: int) -> ThreadingHTTPServer:
    db.migrate()
    store.seed()
    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


def main() -> None:
    load_env()
    port = int(os.environ.get("PORT", "8000"))
    server = make_server(port)
    log("info", "started", port=port, version=VERSION, database="postgres" if os.environ.get("DATABASE_URL") else "sqlite")
    server.serve_forever()


if __name__ == "__main__":
    main()
