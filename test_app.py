"""Runs against SQLite by default, or Postgres when DATABASE_URL is set (CI runs both). Never calls Twelve Data."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

os.environ.pop("TWELVE_DATA_API_KEY", None)
if not os.environ.get("DATABASE_URL"):
    os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

import app  # noqa: E402
import db  # noqa: E402
import score  # noqa: E402

NEWSLETTER = {
    "publisher": "Test Weekly",
    "title": "Three calls for 2026",
    "published": "2026-03-02",
    "message_id": "<abc123@example.com>",
    "calls": [
        {"id": "tech", "who": "Bank A", "call": "Own tech", "track": ["QQQ"], "benchmark": {"ticker": "SPY"}},
        {"who": "Bank B", "call": "Market +10%", "track": ["SPY"], "benchmark": {"target": 10}},
    ],
}


class Scoring(unittest.TestCase):
    returns = {
        "SPY": {"low": 10.0, "high": 10.0, "confidence": "high"},
        "QQQ": {"low": 20.0, "high": 22.0, "confidence": "high"},
        "XLU": {"low": -5.0, "high": -4.0, "confidence": "low"},
    }

    def test_verdict_needs_whole_range_on_one_side(self):
        self.assertEqual(score.verdict(0.5, 3.0), "On track")
        self.assertEqual(score.verdict(-3.0, -0.5), "Off track")
        self.assertEqual(score.verdict(-1.0, 1.0), "Too close to call")

    def test_excess_return_against_ticker(self):
        r = score.score({"track": ["QQQ"], "benchmark": {"ticker": "SPY"}}, self.returns)
        self.assertEqual((r["excess_low"], r["excess_high"], r["status"]), (10.0, 12.0, "On track"))

    def test_basket_takes_lowest_confidence(self):
        r = score.score({"track": ["QQQ", "XLU"], "benchmark": {"target": 5.0}}, self.returns)
        self.assertEqual(r["ret"]["confidence"], "low")

    def test_missing_price_is_no_data(self):
        r = score.score({"track": ["IWD"], "benchmark": {"ticker": "IWF"}}, self.returns)
        self.assertEqual((r["status"], r["missing"]), ("No data", ["IWD", "IWF"]))


class Service(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.reset()
        cls.server = app.make_server(0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def call(self, method, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.headers, resp.read().decode()
        except urllib.error.HTTPError as err:
            with err:
                return err.code, err.headers, err.read().decode()

    def test_health_reports_each_dependency(self):
        status, headers, body = self.call("GET", "/health")
        body = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "degraded")  # no Twelve Data key in tests
        self.assertTrue(body["checks"]["database"]["ok"])
        self.assertFalse(body["checks"]["twelvedata"]["ok"])
        self.assertTrue(headers["X-Request-Id"])

    def test_request_id_is_passed_through(self):
        req = urllib.request.Request(self.base + "/health", headers={"X-Request-Id": "trace-me"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.headers["X-Request-Id"], "trace-me")

    def test_seeded_newsletter_is_listed_and_scored(self):
        status, _, body = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Во что крупнейшие инвестбанки", body)
        nid = next(n["id"] for n in app.store.list_newsletters() if n["publisher"].startswith("Bell"))
        status, _, body = self.call("GET", f"/newsletters/{nid}.json")
        results = json.loads(body)["results"]
        self.assertEqual(len(results), 10)
        self.assertEqual(next(r for r in results if r["id"] == "ubs-utilities")["status"], "Off track")

    def test_same_newsletter_twice_is_not_duplicated(self):
        status, _, first = self.call("POST", "/newsletters", NEWSLETTER)
        self.assertEqual(status, 201)
        status, _, second = self.call("POST", "/newsletters", NEWSLETTER)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(first)["id"], json.loads(second)["id"])
        self.assertFalse(json.loads(second)["created"])
        _, _, body = self.call("GET", json.loads(first)["url"] + ".json")
        self.assertEqual(len(json.loads(body)["results"]), 2)
        listed = [n for n in app.store.list_newsletters() if n["title"] == NEWSLETTER["title"]]
        self.assertEqual(len(listed), 1)

    def test_malformed_input_is_rejected_with_400(self):
        cases = [
            (b"{not json", "not valid JSON"),
            (json.dumps([1, 2]).encode(), "expected a JSON object"),
            (json.dumps({**NEWSLETTER, "published": "02/03/2026"}).encode(), "YYYY-MM-DD"),
            (json.dumps({**NEWSLETTER, "calls": []}).encode(), "1 to 50 calls"),
            (json.dumps({**NEWSLETTER, "calls": [{"who": "X", "call": "Y", "track": ["spy; drop table"], "benchmark": {"ticker": "SPY"}}]}).encode(), "tickers"),
            (json.dumps({**NEWSLETTER, "calls": [{"who": "X", "call": "Y", "track": ["SPY"], "benchmark": {}}]}).encode(), "benchmark"),
        ]
        for raw, expected in cases:
            with self.subTest(expected=expected):
                status, _, body = self.call("POST", "/newsletters", raw=raw)
                self.assertEqual(status, 400)
                self.assertIn(expected, json.loads(body)["error"])

    def test_unknown_paths_are_404(self):
        self.assertEqual(self.call("GET", "/nope")[0], 404)
        self.assertEqual(self.call("GET", "/newsletters/0000000000")[0], 404)
        self.assertEqual(self.call("POST", "/", {})[0], 404)


if __name__ == "__main__":
    unittest.main()
