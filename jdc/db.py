"""SQLite storage for open postings (closed ones are deleted) and the search behind the UI."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .models import Detail, Posting
from .normalize import career_label, dedupe_key, fold, normalize_location, split_terms, term_pattern

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

# Which copy represents a posting that appears on several sites.
SOURCE_PRIORITY = ("wanted", "remember", "jumpit", "jobplanet", "saramin", "jobkorea")
# Posting attributes stored as columns; detail lookups merge into the same keys.
_RECORD_KEYS = ("url", "title", "company", "locations", "career_min", "career_max", "career_text", "skills",
                "categories", "employment_type", "deadline", "posted_at", "description", "extra")
_JSON_COLUMNS = ("locations", "skills", "categories", "extra")
_KEEP_IF_EMPTY = ("description", "posted_at", "employment_type", "career_text", "skills", "categories")
# Closed postings are deleted while scraping; this also hides ones whose deadline passed since.
VISIBLE = "(deadline IS NULL OR deadline >= :today)"
# When a site gives no posting date, the day we first saw it stands in — except for the
# backlog collected by a site's very first run, which would all look like "today".
LISTED_DATE = "COALESCE(posted_at, CASE WHEN seeded = 0 THEN substr(first_seen_at, 1, 10) END)"
_ADDED_COLUMNS = {"seeded": "INTEGER NOT NULL DEFAULT 0"}


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.create_function("jdc_match", 2, _match, deterministic=True)
    conn.executescript(SCHEMA)
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
    for column, ddl in _ADDED_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {ddl}")
    if "status" in existing:  # databases from before closed postings were deleted
        conn.execute("DELETE FROM jobs WHERE status != 'open'")
        conn.commit()
    return conn


def _match(pattern: str, value: str | None) -> bool:
    return bool(value) and re.search(pattern, value) is not None


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


def recent_runs(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT ?", (limit,))]


# -- searching ----------------------------------------------------------------------

@dataclass
class SearchFilter:
    q: str | None = None
    exclude: str | None = None
    title_only: bool = False
    regions: list[str] = field(default_factory=list)
    districts: list[str] = field(default_factory=list)
    years: int | None = None
    sources: list[str] = field(default_factory=list)
    days: int | None = None  # only postings listed within the last N days
    sort: str = "latest"  # latest | deadline
    dedupe: bool = True
    page: int = 1
    size: int = 30


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _term_condition(column: str, term: str, params: dict, name: str) -> str:
    params[name] = _like(term)
    condition = f"{column} LIKE :{name} ESCAPE '\\'"
    if pattern := term_pattern(term):
        params[f"{name}_re"] = pattern.pattern
        condition += f" AND jdc_match(:{name}_re, {column})"
    return condition


def _where(f: SearchFilter, today: str) -> tuple[str, dict]:
    clauses = [VISIBLE]
    params: dict = {"today": today}
    if f.sources:
        names = [f"src{i}" for i in range(len(f.sources))]
        clauses.append(f"source IN ({', '.join(':' + n for n in names)})")
        params.update(zip(names, f.sources))
    for col, values in (("regions", f.regions), ("districts", f.districts)):
        if values:
            names = [f"{col}{i}" for i in range(len(values))]
            clauses.append("(" + " OR ".join(f"instr({col}, :{n}) > 0" for n in names) + ")")
            params.update({n: f"|{v}|" for n, v in zip(names, values)})
    if f.years is not None:
        clauses.append("(career_min IS NULL OR career_min <= :years) AND (career_max IS NULL OR career_max >= :years)")
        params["years"] = f.years
    if f.days:
        clauses.append(f"{LISTED_DATE} >= :since")
        params["since"] = (date.fromisoformat(today) - timedelta(days=f.days)).isoformat()
    column = "title_text" if f.title_only else "search_text"
    for i, term in enumerate(split_terms(f.q)):
        clauses.append(f"({_term_condition(column, term, params, f'q{i}')})")
    for i, term in enumerate(split_terms(f.exclude)):
        clauses.append(f"NOT ({_term_condition('title_text', term, params, f'x{i}')})")
    return " AND ".join(clauses), params


_ORDER = {
    "latest": "sort_date DESC, id DESC",
    "deadline": "deadline IS NULL, deadline ASC, sort_date DESC, id DESC",
}
_LIST_COLUMNS = (
    "id, source, source_id, url, title, company, location_text, regions, career_min, career_max, career_text, "
    "skills, categories, employment_type, deadline, posted_at, first_seen_at, extra, dedupe_key"
)


def search(conn: sqlite3.Connection, f: SearchFilter, today: str) -> dict:
    where, params = _where(f, today)
    size = max(1, min(f.size, 100))
    page = max(1, f.page)
    rank = "CASE source " + " ".join(f"WHEN '{s}' THEN {i}" for i, s in enumerate(SOURCE_PRIORITY)) + " ELSE 9 END"
    partition = "dedupe_key" if f.dedupe else "id"
    sql = f"""
        WITH filtered AS (
            SELECT {_LIST_COLUMNS}, {LISTED_DATE} AS sort_date, {rank} AS source_rank
            FROM jobs WHERE {where}
        ), ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY {partition} ORDER BY source_rank, id) AS rn
            FROM filtered
        )
        SELECT * FROM ranked WHERE rn = 1 ORDER BY {_ORDER.get(f.sort, _ORDER['latest'])}
        LIMIT :limit OFFSET :offset
    """
    rows = conn.execute(sql, {**params, "limit": size, "offset": (page - 1) * size}).fetchall()
    count_expr = "COUNT(DISTINCT dedupe_key)" if f.dedupe else "COUNT(*)"
    total = conn.execute(f"SELECT {count_expr} FROM jobs WHERE {where}", params).fetchone()[0]
    items = [_list_item(r, today) for r in rows]
    if f.dedupe and items:
        _attach_other_sources(conn, items, today)
    return {"total": total, "page": page, "size": size, "items": items}


def _list_item(row: sqlite3.Row, today: str) -> dict:
    rec = dict(row)
    extra = json.loads(rec.pop("extra") or "{}")
    listed = rec["sort_date"]
    days_left = (date.fromisoformat(rec["deadline"]) - date.fromisoformat(today)).days if rec["deadline"] else None
    return {
        "id": rec["id"],
        "source": rec["source"],
        "url": rec["url"],
        "title": rec["title"],
        "company": rec["company"],
        "location": rec["location_text"],
        "regions": [r for r in (rec.get("regions") or "").split("|") if r],
        "career": career_label(rec["career_min"], rec["career_max"], rec["career_text"]),
        "career_min": rec["career_min"],
        "career_max": rec["career_max"],
        "skills": json.loads(rec["skills"] or "[]"),
        "categories": json.loads(rec["categories"] or "[]"),
        "employment_type": rec["employment_type"],
        "deadline": rec["deadline"],
        "days_left": days_left,
        "listed_at": listed or None,
        "is_new": bool(listed) and listed >= (date.fromisoformat(today) - timedelta(days=2)).isoformat(),
        "thumbnail": extra.get("thumbnail"),
        "dedupe_key": rec["dedupe_key"],
        "also_on": [],
    }


def _attach_other_sources(conn: sqlite3.Connection, items: list[dict], today: str) -> None:
    keys = sorted({item["dedupe_key"] for item in items})
    marks = ", ".join(f":k{i}" for i in range(len(keys)))
    rows = conn.execute(
        f"SELECT id, source, url, dedupe_key FROM jobs WHERE {VISIBLE} AND dedupe_key IN ({marks})",
        {"today": today, **{f"k{i}": k for i, k in enumerate(keys)}},
    ).fetchall()
    by_key: dict[str, list[dict]] = {}
    for r in rows:
        by_key.setdefault(r["dedupe_key"], []).append({"id": r["id"], "source": r["source"], "url": r["url"]})
    for item in items:
        item["also_on"] = [o for o in by_key.get(item["dedupe_key"], []) if o["id"] != item["id"]]


def get_job(conn: sqlite3.Connection, job_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    rec = _decode(row)
    return {
        "id": rec["id"], "source": rec["source"], "url": rec["url"], "title": rec["title"],
        "company": rec["company"], "locations": rec["locations"], "location": rec["location_text"],
        "career": career_label(rec["career_min"], rec["career_max"], rec["career_text"]),
        "skills": rec["skills"], "categories": rec["categories"], "employment_type": rec["employment_type"],
        "deadline": rec["deadline"], "posted_at": rec["posted_at"], "description": rec["description"],
        "first_seen_at": rec["first_seen_at"], "last_seen_at": rec["last_seen_at"],
    }


def facets(conn: sqlite3.Connection, today: str) -> dict:
    rows = conn.execute(f"SELECT source, regions, districts FROM jobs WHERE {VISIBLE}", {"today": today}).fetchall()
    sources: Counter = Counter()
    regions: Counter = Counter()
    districts: Counter = Counter()
    for r in rows:
        sources[r["source"]] += 1
        regions.update(x for x in r["regions"].split("|") if x)
        districts.update(x for x in r["districts"].split("|") if x)
    unique_total = conn.execute(
        f"SELECT COUNT(DISTINCT dedupe_key) FROM jobs WHERE {VISIBLE}", {"today": today}
    ).fetchone()[0]
    grouped: dict[str, list[dict]] = {}
    for name, count in districts.most_common():
        region = name.split(" ", 1)[0]
        grouped.setdefault(region, []).append({"name": name, "count": count})
    return {
        "total": len(rows),
        "unique_total": unique_total,
        "sources": dict(sources),
        "regions": [{"name": n, "count": c} for n, c in regions.most_common()],
        "districts": grouped,
    }
