"""SQLite storage for open postings (closed ones are deleted): the collector's working copy."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

from .models import Detail, Posting
from .normalize import dedupe_key, fold, normalize_location

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    locations TEXT NOT NULL DEFAULT '[]',
    location_text TEXT NOT NULL DEFAULT '',
    regions TEXT NOT NULL DEFAULT '',      -- '|서울|경기|'
    districts TEXT NOT NULL DEFAULT '',    -- '|서울 강남구|'
    career_min INTEGER,
    career_max INTEGER,
    career_text TEXT,
    skills TEXT NOT NULL DEFAULT '[]',
    categories TEXT NOT NULL DEFAULT '[]',
    employment_type TEXT,
    deadline TEXT,                         -- YYYY-MM-DD inclusive, NULL = 상시
    posted_at TEXT,
    description TEXT,
    extra TEXT NOT NULL DEFAULT '{}',
    search_text TEXT NOT NULL DEFAULT '',
    title_text TEXT NOT NULL DEFAULT '',
    dedupe_key TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_checked_at TEXT,
    detail_fetched_at TEXT,
    detail_attempts INTEGER NOT NULL DEFAULT 0,
    missing_runs INTEGER NOT NULL DEFAULT 0,
    seeded INTEGER NOT NULL DEFAULT 0,     -- inserted by a site's first run: first_seen_at is not a posting date
    UNIQUE (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_jobs_deadline ON jobs (deadline);
CREATE INDEX IF NOT EXISTS idx_jobs_source_seen ON jobs (source, last_seen_at);
CREATE INDEX IF NOT EXISTS idx_jobs_dedupe ON jobs (dedupe_key);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,                  -- running | ok | partial | failed
    listed INTEGER NOT NULL DEFAULT 0,
    new INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    closed INTEGER NOT NULL DEFAULT 0,      -- postings deleted as closed
    details INTEGER NOT NULL DEFAULT 0,
    verified INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""

# Posting attributes stored as columns; detail lookups merge into the same keys.
_RECORD_KEYS = ("url", "title", "company", "locations", "career_min", "career_max", "career_text", "skills",
                "categories", "employment_type", "deadline", "posted_at", "description", "extra")
_JSON_COLUMNS = ("locations", "skills", "categories", "extra")
_KEEP_IF_EMPTY = ("description", "posted_at", "employment_type", "career_text", "skills", "categories")
# Closed postings are deleted while scraping; this also hides ones whose deadline passed since.
VISIBLE = "(deadline IS NULL OR deadline >= :today)"
_ADDED_COLUMNS = {"seeded": "INTEGER NOT NULL DEFAULT 0"}


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
    for column, ddl in _ADDED_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {ddl}")
    if "status" in existing:  # databases from before closed postings were deleted
        conn.execute("DELETE FROM jobs WHERE status != 'open'")
        conn.commit()
    return conn


# -- writing ----------------------------------------------------------------------

def _record(posting: Posting) -> dict:
    return {key: getattr(posting, key) for key in _RECORD_KEYS}


def _decode(row: sqlite3.Row) -> dict:
    rec = dict(row)
    for col in _JSON_COLUMNS:
        rec[col] = json.loads(rec[col]) if rec.get(col) else ([] if col != "extra" else {})
    return rec


def _regions_of(locations: list[str]) -> tuple[list[str], list[str]]:
    regions: list[str] = []
    districts: list[str] = []
    for loc in locations:
        region, district = normalize_location(loc)
        if region and region not in regions:
            regions.append(region)
        if district and district not in districts:
            districts.append(district)
    return regions, districts


def _merge(current: dict, incoming: dict) -> dict:
    merged = dict(current)
    for key, value in incoming.items():
        if key in _KEEP_IF_EMPTY and not value:
            continue
        if key == "locations":
            if not value:
                continue
            new_regions, new_districts = _regions_of(value)
            old_regions, old_districts = _regions_of(current.get("locations") or [])
            known = lambda regions: [r for r in regions if r != "기타"]  # noqa: E731
            # Keep what we have when the new value says less: an unparseable address,
            # or a listing's bare "서울" after the detail page gave the street address.
            if known(old_regions) and not known(new_regions):
                continue
            if old_districts and not new_districts and set(new_regions) <= set(old_regions):
                continue
        if key == "extra":
            value = {**(current.get("extra") or {}), **{k: v for k, v in (value or {}).items() if v is not None}}
        merged[key] = value
    return merged


def _derived(rec: dict) -> dict:
    regions, districts = _regions_of(rec.get("locations") or [])
    places = districts or regions
    location_text = places[0] if places else ""
    if len(places) > 1:
        location_text += f" 외 {len(places) - 1}"
    skills = " ".join(rec.get("skills") or [])
    categories = " ".join(rec.get("categories") or [])
    head = " ".join([rec["title"], rec["company"], skills, categories])
    return {
        "regions": f"|{'|'.join(regions)}|" if regions else "",
        "districts": f"|{'|'.join(districts)}|" if districts else "",
        "location_text": location_text,
        "title_text": fold(head),
        "search_text": fold(" ".join([head, rec.get("employment_type") or "", rec.get("description") or ""])),
        "dedupe_key": dedupe_key(rec["company"], rec["title"]),
    }


def _write(conn: sqlite3.Connection, job_id: int, rec: dict, **extra_columns) -> None:
    values = {k: rec[k] for k in _RECORD_KEYS}
    for col in _JSON_COLUMNS:
        values[col] = json.dumps(values[col], ensure_ascii=False)
    values.update(_derived(rec))
    values.update(extra_columns)
    assignments = ", ".join(f"{k} = :{k}" for k in values)
    conn.execute(f"UPDATE jobs SET {assignments} WHERE id = :_id", {**values, "_id": job_id})


def _delete(conn: sqlite3.Connection, source: str, source_id: str) -> bool:
    cur = conn.execute("DELETE FROM jobs WHERE source = ? AND source_id = ?", (source, source_id))
    return cur.rowcount > 0


def upsert_listing(conn: sqlite3.Connection, posting: Posting, now: str, today: str, *, seeding: bool = False) -> str:
    """Store a posting seen in a site's listing. Returns new | updated | closed | skipped.

    A posting the listing marks closed, or whose deadline has passed, is deleted ('closed'),
    or never stored if we had not seen it before ('skipped').
    """
    if not posting.is_open or (posting.deadline and posting.deadline < today):
        return "closed" if _delete(conn, posting.source, posting.source_id) else "skipped"
    incoming = _record(posting)
    row = conn.execute(
        "SELECT * FROM jobs WHERE source = ? AND source_id = ?", (posting.source, posting.source_id)
    ).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO jobs (source, source_id, url, title, company, first_seen_at, last_seen_at, seeded) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (posting.source, posting.source_id, posting.url, posting.title, posting.company, now, now, int(seeding)),
        )
        _write(conn, cur.lastrowid, incoming)
        return "new"
    current = _decode(row)
    _write(conn, current["id"], _merge(current, incoming), last_seen_at=now, missing_runs=0)
    return "updated"


def apply_detail(conn: sqlite3.Connection, source: str, source_id: str, detail: Detail, now: str) -> str:
    """Merge a detail lookup into the stored posting, or delete it if closed. Returns open | closed | unknown."""
    row = conn.execute("SELECT * FROM jobs WHERE source = ? AND source_id = ?", (source, source_id)).fetchone()
    if row is None:
        return "unknown"
    current = _decode(row)
    if detail.state == "open":
        _write(conn, current["id"], _merge(current, detail.fields),
               detail_fetched_at=now, last_checked_at=now)
        return "open"
    if detail.state in ("closed", "missing"):
        _delete(conn, source, source_id)
        return "closed"
    conn.execute(
        "UPDATE jobs SET detail_attempts = detail_attempts + 1, last_checked_at = ? WHERE id = ?",
        (now, current["id"]),
    )
    return "unknown"


def rederive(conn: sqlite3.Connection) -> int:
    """Recompute regions, search text and dedupe keys after normalization rules change."""
    rows = conn.execute("SELECT * FROM jobs").fetchall()
    for row in rows:
        rec = _decode(row)
        _write(conn, rec["id"], rec)
    conn.commit()
    return len(rows)


def ids_needing_detail(conn: sqlite3.Connection, source: str, limit: int) -> list[str]:
    rows = conn.execute(
        "SELECT source_id FROM jobs WHERE source = ? AND detail_fetched_at IS NULL "
        "AND detail_attempts < 3 ORDER BY first_seen_at DESC, id DESC LIMIT ?",
        (source, limit),
    ).fetchall()
    return [r["source_id"] for r in rows]


def open_ids_not_seen(conn: sqlite3.Connection, source: str, since: str, limit: int) -> list[str]:
    """Stored postings a complete listing did not include — candidates for deletion."""
    rows = conn.execute(
        "SELECT source_id FROM jobs WHERE source = ? AND last_seen_at < ? "
        "ORDER BY last_checked_at IS NOT NULL, last_checked_at LIMIT ?",
        (source, since, limit),
    ).fetchall()
    return [r["source_id"] for r in rows]


def count_postings(conn: sqlite3.Connection, source: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM jobs WHERE source = ?", (source,)).fetchone()[0]


def has_postings(conn: sqlite3.Connection, source: str) -> bool:
    return conn.execute("SELECT 1 FROM jobs WHERE source = ? LIMIT 1", (source,)).fetchone() is not None


def bump_missing(conn: sqlite3.Connection, source: str, source_id: str, threshold: int) -> bool:
    """Count an inconclusive check for an unlisted posting; delete it once it keeps happening."""
    conn.execute(
        "UPDATE jobs SET missing_runs = missing_runs + 1 WHERE source = ? AND source_id = ?", (source, source_id)
    )
    cur = conn.execute(
        "DELETE FROM jobs WHERE source = ? AND source_id = ? AND missing_runs >= ?", (source, source_id, threshold)
    )
    return cur.rowcount > 0


def delete_expired(conn: sqlite3.Connection, today: str) -> int:
    cur = conn.execute("DELETE FROM jobs WHERE deadline IS NOT NULL AND deadline < ?", (today,))
    return cur.rowcount


# -- scrape runs --------------------------------------------------------------------

def start_run(conn: sqlite3.Connection, source: str, now: str) -> int:
    cur = conn.execute("INSERT INTO scrape_runs (source, started_at, status) VALUES (?, ?, 'running')", (source, now))
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, status: str, stats: Counter, now: str,
               error: str | None = None) -> None:
    conn.execute(
        "UPDATE scrape_runs SET finished_at = ?, status = ?, listed = ?, new = ?, updated = ?, "
        "closed = ?, details = ?, verified = ?, error = ? WHERE id = ?",
        (now, status, stats["listed"], stats["new"], stats["updated"], stats["closed"],
         stats["details"], stats["verified"], error, run_id),
    )
    conn.commit()


def fail_stale_runs(conn: sqlite3.Connection, now: str) -> None:
    """Runs left 'running' by a killed process."""
    conn.execute(
        "UPDATE scrape_runs SET status = 'failed', finished_at = ?, error = '중단됨' WHERE status = 'running'", (now,)
    )
    conn.commit()


def latest_runs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM scrape_runs WHERE id IN (SELECT MAX(id) FROM scrape_runs GROUP BY source) ORDER BY source"
    ).fetchall()
    return [dict(r) for r in rows]
