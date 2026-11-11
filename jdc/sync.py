"""Mirror the collector's SQLite into the Supabase database the web app reads.

SQLite stays the collector's working copy (when a posting was last listed, how many checks came
back inconclusive). Supabase only receives what the viewer needs, once a scrape has finished:
new or changed postings are uploaded, postings deleted locally are deleted there, and all of it
lands in one transaction so the viewer never sees a half-finished state.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date

import psycopg
from psycopg.conninfo import conninfo_to_dict

from . import db
from .config import Settings
from .normalize import career_label, now_kst, today_kst

log = logging.getLogger(__name__)
# Columns of public.jobs the collector writes, in upload order. content_hash covers all the others.
COLUMNS = (
    "source", "source_id", "url", "title", "company", "locations", "location_text", "regions", "districts",
    "career_min", "career_max", "career", "skills", "categories", "employment_type", "deadline", "posted_at",
    "listed_at", "description", "title_text", "search_text", "dedupe_key", "content_hash",
)
# Below this many stored postings, a large share going away is not alarming.
_GUARD_MIN_STORED = 50
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")  # the local Supabase for development has no TLS


class SyncError(RuntimeError):
    """The upload can't go ahead; the message says why and what to do."""


@dataclass(frozen=True)
class SyncResult:
    uploaded: int
    deleted: int
    total: int


def _clean(value: str | None) -> str | None:
    """Postgres text can't hold NUL bytes, which SQLite and scraped pages can."""
    return value.replace("\x00", "") if value else value


def _clean_list(values: list) -> list[str]:
    return [_clean(str(v)) for v in values if v]


def _split_marked(value: str) -> list[str]:
    return [part for part in value.split("|") if part]  # '|서울|경기|'


def _date(value: str | None) -> str | None:
    """A malformed date from a site must not fail the whole upload."""
    try:
        return date.fromisoformat(value[:10]).isoformat() if value else None
    except ValueError:
        return None


def _row(rec: sqlite3.Row) -> dict:
    posted_at = _date(rec["posted_at"])
    row = {
        "source": rec["source"],
        "source_id": rec["source_id"],
        "url": _clean(rec["url"]),
        "title": _clean(rec["title"]),
        "company": _clean(rec["company"]),
        "locations": _clean_list(json.loads(rec["locations"] or "[]")),
        "location_text": _clean(rec["location_text"]),
        "regions": _split_marked(rec["regions"]),
        "districts": _split_marked(rec["districts"]),
        "career_min": rec["career_min"],
        "career_max": rec["career_max"],
        "career": _clean(career_label(rec["career_min"], rec["career_max"], rec["career_text"])),
        "skills": _clean_list(json.loads(rec["skills"] or "[]")),
        "categories": _clean_list(json.loads(rec["categories"] or "[]")),
        "employment_type": _clean(rec["employment_type"]),
        "deadline": _date(rec["deadline"]),
        "posted_at": posted_at,
        # A site's first run stored its whole backlog at once, so that day says nothing about the posting.
        "listed_at": posted_at or (None if rec["seeded"] else _date(rec["first_seen_at"])),
        "description": _clean(rec["description"]),
        "title_text": _clean(rec["title_text"]),
        "search_text": _clean(rec["search_text"]),
        "dedupe_key": _clean(rec["dedupe_key"]),
    }
    row["content_hash"] = hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]
    return row


def local_rows(local: sqlite3.Connection, today: str) -> list[dict]:
    """What the viewer should hold. Oldest first, so ids upstream keep the order postings appeared in."""
    rows = local.execute(f"SELECT * FROM jobs WHERE {db.VISIBLE} ORDER BY id", {"today": today})
    return [_row(rec) for rec in rows]


def push(local: sqlite3.Connection, remote: psycopg.Connection, today: str, now: str, *, force: bool = False) -> SyncResult:
    rows = local_rows(local, today)
    names = ", ".join(COLUMNS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in COLUMNS if c not in ("source", "source_id"))
    with remote.transaction(), remote.cursor() as cur:
        stored = {(s, i): h for s, i, h in cur.execute("SELECT source, source_id, content_hash FROM public.jobs")}
        keep = {(r["source"], r["source_id"]) for r in rows}
        gone = [key for key in stored if key not in keep]
        changed = [r for r in rows if stored.get((r["source"], r["source_id"])) != r["content_hash"]]

        if not force and len(stored) > _GUARD_MIN_STORED and len(gone) > len(stored) * 0.5:
            raise SyncError(
                f"Supabase의 공고 {len(stored):,}건 중 {len(gone):,}건을 지우게 되어 업로드를 멈췄습니다. "
                "로컬 데이터 폴더(JDC_DATA_DIR)가 맞는지 확인해 주세요. 의도한 것이라면 --force를 붙입니다."
            )
        if gone:
            cur.execute(
                "DELETE FROM public.jobs AS j USING unnest(%s::text[], %s::text[]) AS g(source, source_id) "
                "WHERE j.source = g.source AND j.source_id = g.source_id",
                ([s for s, _ in gone], [i for _, i in gone]),
            )
        if changed:
            cur.execute(f"CREATE TEMP TABLE incoming ON COMMIT DROP AS SELECT {names} FROM public.jobs WITH NO DATA")
            with cur.copy(f"COPY incoming ({names}) FROM STDIN") as copy:
                for row in changed:
                    copy.write_row([row[c] for c in COLUMNS])
            cur.execute(
                f"INSERT INTO public.jobs ({names}) SELECT {names} FROM incoming "
                f"ON CONFLICT (source, source_id) DO UPDATE SET {updates}"
            )
            cur.execute("DROP TABLE incoming")

        cur.execute("DELETE FROM public.scrape_runs")
        cur.executemany(
            "INSERT INTO public.scrape_runs (source, status, started_at, finished_at, listed, added, closed, error) "
            "VALUES (%(source)s, %(status)s, %(started_at)s, %(finished_at)s, %(listed)s, %(new)s, %(closed)s, %(error)s)",
            [{**run, "error": _clean(run["error"])} for run in db.latest_runs(local)],
        )
        cur.execute(
            "INSERT INTO public.sync_state (id, synced_at) VALUES (true, %s) "
            "ON CONFLICT (id) DO UPDATE SET synced_at = excluded.synced_at",
            (now,),
        )
    return SyncResult(uploaded=len(changed), deleted=len(gone), total=len(rows))


def _connect(settings: Settings) -> psycopg.Connection:
    if not settings.supabase_db_url:
        raise SyncError("JDC_SUPABASE_DB_URL이 없습니다. README의 'Supabase 준비'를 따라 .env에 넣어 주세요.")
    options = conninfo_to_dict(settings.supabase_db_url)
    # The password and the data cross the internet, so don't let the connection fall back to plain text.
    sslmode = options.get("sslmode") or ("disable" if options.get("host") in LOCAL_HOSTS else "require")
    # prepare_threshold=None: connection poolers may hand each statement a different server session.
    return psycopg.connect(settings.supabase_db_url, sslmode=sslmode, prepare_threshold=None, connect_timeout=20)


def run_sync(settings: Settings, *, force: bool = False) -> SyncResult:
    from .pipeline import AlreadyRunning, ScrapeLock

    with ScrapeLock(settings.lock_path) as acquired:
        if not acquired:
            raise AlreadyRunning("수집이 진행 중입니다. 끝나면 자동으로 올라갑니다")
        local = db.connect(settings.db_path)
        try:
            db.fail_stale_runs(local, now_kst().isoformat())  # we hold the lock, so nothing is really running
            with _connect(settings) as remote:
                result = push(local, remote, today_kst(), now_kst().isoformat(), force=force)
        finally:
            local.close()
    log.info("synced: %s", result)
    return result


def add_viewer(remote: psycopg.Connection, email: str) -> bool:
    """Allow an existing Supabase account to read the postings. False if there is no such account."""
    row = remote.execute("SELECT id FROM auth.users WHERE lower(email) = lower(%s)", (email,)).fetchone()
    if row is None:
        return False
    remote.execute("INSERT INTO private.viewers (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (row[0],))
    return True


def grant_viewer(settings: Settings, email: str) -> bool:
    with _connect(settings) as remote:
        return add_viewer(remote, email)
