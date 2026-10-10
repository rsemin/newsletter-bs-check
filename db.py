import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from logs import log

HERE = Path(__file__).parent

# Append-only. Never edit a migration that has shipped: add a new one. Keep them additive
# (new tables, nullable columns) so the previous release still works if we roll back.
MIGRATIONS = [
    (1, [
        """CREATE TABLE newsletters (
            id TEXT PRIMARY KEY,
            natural_key TEXT NOT NULL UNIQUE,
            publisher TEXT NOT NULL,
            title TEXT NOT NULL,
            published TEXT NOT NULL,
            baseline TEXT NOT NULL,
            created_at TEXT NOT NULL)""",
        """CREATE TABLE calls (
            newsletter_id TEXT NOT NULL REFERENCES newsletters(id),
            call_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            who TEXT NOT NULL,
            summary TEXT NOT NULL,
            thesis TEXT NOT NULL,
            quote TEXT NOT NULL,
            track TEXT NOT NULL,
            benchmark TEXT NOT NULL,
            explanation TEXT,
            PRIMARY KEY (newsletter_id, call_id))""",
        """CREATE TABLE prices (
            ticker TEXT NOT NULL,
            baseline TEXT NOT NULL,
            low DOUBLE PRECISION NOT NULL,
            high DOUBLE PRECISION NOT NULL,
            as_of TEXT NOT NULL,
            confidence TEXT NOT NULL,
            source TEXT NOT NULL,
            sources TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (ticker, baseline))""",
    ]),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Conn:
    """One connection, one transaction: commits on success, rolls back on error, always closes."""

    def __init__(self, raw, placeholder: str):
        self.raw, self.placeholder = raw, placeholder

    def all(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self.raw.execute(sql.replace("?", self.placeholder), params)
        return [dict(r) for r in cur.fetchall()] if cur.description else []

    def one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def __enter__(self) -> "Conn":
        return self

    def __exit__(self, exc_type, *_) -> None:
        try:
            self.raw.rollback() if exc_type else self.raw.commit()
        finally:
            self.raw.close()


def connect() -> Conn:
    """Postgres when DATABASE_URL is set (production, CI), otherwise a local SQLite file."""
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith(("postgres://", "postgresql://")):
        import psycopg
        from psycopg.rows import dict_row

        return Conn(psycopg.connect(url, row_factory=dict_row, connect_timeout=5), "%s")
    raw = sqlite3.connect(os.environ.get("SQLITE_PATH", str(HERE / "data" / "local.db")), timeout=10)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    return Conn(raw, "?")


def migrate() -> None:
    with connect() as c:
        c.all("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        done = {r["version"] for r in c.all("SELECT version FROM schema_migrations")}
        for version, statements in MIGRATIONS:
            if version in done:
                continue
            for sql in statements:
                c.all(sql)
            c.all("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (version, now()))
            log("info", "migration applied", version=version)


def reset() -> None:
    """Tests only: drop everything."""
    with connect() as c:
        for table in ("prices", "calls", "newsletters", "schema_migrations"):
            c.all(f"DROP TABLE IF EXISTS {table}")
