from __future__ import annotations

import sqlite3
import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from backend.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    task TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    official_domain TEXT,
    allowed_domains TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    finished_at REAL,
    final_answer TEXT,
    error TEXT,
    pages_fetched INTEGER DEFAULT 0,
    pages_failed INTEGER DEFAULT 0,
    llm_calls INTEGER DEFAULT 0,
    iterations INTEGER DEFAULT 0,
    coverage_note TEXT
);

CREATE TABLE IF NOT EXISTS urls (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'discovered',
    discovered_from TEXT,
    relevance_reason TEXT,
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    domain TEXT,
    created_at REAL NOT NULL,
    UNIQUE(run_id, canonical_url)
);

CREATE TABLE IF NOT EXISTS pages (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    url_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    fetched_with TEXT,
    content_hash TEXT,
    text_excerpt TEXT,
    full_text_path TEXT,
    fetched_at REAL NOT NULL,
    http_status INTEGER
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    url TEXT NOT NULL,
    kind TEXT NOT NULL,
    snippet TEXT NOT NULL,
    note TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS citations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    valid INTEGER DEFAULT 1,
    invalid_reason TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT
);
"""


def new_id() -> str:
    return uuid.uuid4().hex[:16]


@contextmanager
def get_conn():
    Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def log_event(run_id: str, kind: str, detail: dict):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events (id, run_id, ts, kind, detail) VALUES (?, ?, ?, ?, ?)",
            (new_id(), run_id, time.time(), kind, json.dumps(detail, default=str)[:8000]),
        )


def create_run(target: str, task: str) -> str:
    run_id = new_id()
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO runs (id, target, task, status, created_at, updated_at) VALUES (?, ?, ?, 'pending', ?, ?)",
            (run_id, target, task, now, now),
        )
    return run_id


def update_run(run_id: str, **fields):
    if not fields:
        return
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [run_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE runs SET {cols} WHERE id = ?", values)


def get_run(run_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None


def get_events(run_id: str, limit: int = 500) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY ts ASC LIMIT ?", (run_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_url(run_id: str, url: str, canonical_url: str, discovered_from: str | None, domain: str) -> str:
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM urls WHERE run_id = ? AND canonical_url = ?", (run_id, canonical_url)
        ).fetchone()
        if existing:
            return existing["id"]
        url_id = new_id()
        conn.execute(
            "INSERT INTO urls (id, run_id, url, canonical_url, status, discovered_from, domain, created_at) "
            "VALUES (?, ?, ?, ?, 'discovered', ?, ?, ?)",
            (url_id, run_id, url, canonical_url, discovered_from, domain, time.time()),
        )
        return url_id


def set_url_status(url_id: str, status: str, relevance_reason: str | None = None, last_error: str | None = None):
    with get_conn() as conn:
        fields = {"status": status}
        if relevance_reason is not None:
            fields["relevance_reason"] = relevance_reason
        if last_error is not None:
            fields["last_error"] = last_error
        cols = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE urls SET {cols} WHERE id = ?", list(fields.values()) + [url_id])


def increment_attempts(url_id: str):
    with get_conn() as conn:
        conn.execute("UPDATE urls SET attempts = attempts + 1 WHERE id = ?", (url_id,))


def get_urls_by_status(run_id: str, status: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM urls WHERE run_id = ? AND status = ? ORDER BY created_at ASC", (run_id, status)
        ).fetchall()
        return [dict(r) for r in rows]


def count_urls(run_id: str, status: str | None = None) -> int:
    with get_conn() as conn:
        if status:
            row = conn.execute(
                "SELECT COUNT(*) c FROM urls WHERE run_id = ? AND status = ?", (run_id, status)
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) c FROM urls WHERE run_id = ?", (run_id,)).fetchone()
        return row["c"]


def save_page(run_id: str, url_id: str, url: str, title: str, fetched_with: str,
              content_hash: str, text_excerpt: str, full_text_path: str, http_status: int) -> str:
    page_id = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO pages (id, run_id, url_id, url, title, fetched_with, content_hash, "
            "text_excerpt, full_text_path, fetched_at, http_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (page_id, run_id, url_id, url, title, fetched_with, content_hash, text_excerpt,
             full_text_path, time.time(), http_status),
        )
    return page_id


def page_exists_with_hash(run_id: str, content_hash: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM pages WHERE run_id = ? AND content_hash = ?", (run_id, content_hash)
        ).fetchone()
        return row is not None


def save_evidence(run_id: str, page_id: str, url: str, kind: str, snippet: str, note: str = "") -> str:
    ev_id = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO evidence (id, run_id, page_id, url, kind, snippet, note, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (ev_id, run_id, page_id, url, kind, snippet, note, time.time()),
        )
    return ev_id


def get_evidence(run_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM evidence WHERE run_id = ? ORDER BY created_at ASC", (run_id,)).fetchall()
        return [dict(r) for r in rows]


def save_citation(run_id: str, evidence_id: str, claim_text: str, valid: bool, invalid_reason: str | None) -> str:
    cid = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO citations (id, run_id, evidence_id, claim_text, valid, invalid_reason) VALUES (?,?,?,?,?,?)",
            (cid, run_id, evidence_id, claim_text, int(valid), invalid_reason),
        )
    return cid


def get_citations(run_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.*, e.url as source_url, e.snippet as source_snippet, e.kind as evidence_kind
               FROM citations c JOIN evidence e ON c.evidence_id = e.id
               WHERE c.run_id = ? ORDER BY c.rowid ASC""",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_pages(run_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM pages WHERE run_id = ? ORDER BY fetched_at ASC", (run_id,)).fetchall()
        return [dict(r) for r in rows]
