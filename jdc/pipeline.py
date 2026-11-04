"""One scrape run: read every site's listing, enrich new postings, delete closed ones.

Closed postings are detected three ways, from cheapest to most expensive, and deleted:
  1. the listing itself says so, or the deadline has passed (also hidden at query time);
  2. a posting that a *complete* listing no longer contains is looked up on its detail
     page; 'closed' or 'not found' deletes it right away;
  3. if that lookup stays inconclusive for several runs, the posting is deleted anyway.
A listing that failed half-way never triggers 2 or 3, so a site hiccup can't wipe postings.
"""
from __future__ import annotations

import logging
import os
import threading
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from . import db
from .browser import Browser
from .config import Settings
from .normalize import now_kst, today_kst
from .scrapers import SCRAPERS

log = logging.getLogger(__name__)
# Detail reason for a request that never got an HTTP response (network error, or a
# rate limit answered without CORS headers).
NO_RESPONSE = "http:0"


@dataclass
class RunState:
    """Progress of the scrape running in this process, for the UI."""

    running: bool = False
    source: str | None = None
    phase: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


STATE = RunState()


class AlreadyRunning(RuntimeError):
    pass


class ScrapeLock:
    """Cross-process lock so the CLI and the server never drive the browser at once."""

    def __init__(self, path):
        self.path = path
        self.handle = None

    def __enter__(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            return False
        return True

    def __exit__(self, *exc) -> None:
        if self.handle is not None:
            self.handle.close()  # closing releases the lock
            self.handle = None


def _chunks(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def run_scrape(settings: Settings, sources: Iterable[str] | None = None, *, details: bool = True) -> list[dict]:
    sources = list(sources or settings.sources)
    with ScrapeLock(settings.lock_path) as acquired:
        if not acquired:
            raise AlreadyRunning("다른 수집이 이미 진행 중입니다")
        STATE.running, STATE.started_at, STATE.finished_at, STATE.error = True, now_kst().isoformat(), None, None
        conn = db.connect(settings.db_path)
        try:
            db.fail_stale_runs(conn, now_kst().isoformat())
            summaries = []
            with Browser(settings) as browser:
                for source in sources:
                    summaries.append(run_source(conn, browser, source, settings, details=details))
            expired = db.delete_expired(conn, today_kst())
            conn.commit()
            log.info("deleted %d postings past their deadline", expired)
            return summaries
        except Exception as e:
            STATE.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            conn.close()
            STATE.running, STATE.source, STATE.phase = False, None, None
            STATE.finished_at = now_kst().isoformat()


def run_source(conn, browser: Browser, source: str, settings: Settings, *, details: bool = True) -> dict:
    scraper_cls = SCRAPERS[source]
    started = now_kst().isoformat()
    run_id = db.start_run(conn, source, started)
    stats: Counter = Counter()
    status, error = "ok", None
    stored_before = db.count_postings(conn, source)
    seeding = not db.has_postings(conn, source)  # first run: the backlog has no meaningful "first seen" date
    STATE.source, STATE.phase = source, "목록 수집"
    log.info("[%s] listing…", source)
    try:
        tab = browser.open(scraper_cls.home_url)
        scraper = scraper_cls(tab, settings)
        scraper.prepare()

        today = today_kst()
        for batch in scraper.iter_listing():
            now = now_kst().isoformat()
            for posting in batch:
                stats["listed"] += 1
                stats[db.upsert_listing(conn, posting, now, today, seeding=seeding)] += 1
            conn.commit()
        log.info("[%s] listed %d (new %d)", source, stats["listed"], stats["new"])

        complete = scraper.listing_complete
        if complete and stored_before > 50 and stats["listed"] < stored_before * 0.5:
            log.warning("[%s] listing shrank from %d to %d; skipping the closed-posting sweep",
                        source, stored_before, stats["listed"])
            complete = False

        if details and scraper.enrich_with_details:
            STATE.phase = "상세 정보"
            pending = db.ids_needing_detail(conn, source, settings.max_details)
            log.info("[%s] fetching %d details…", source, len(pending))
            for chunk in _chunks(pending, scraper.detail_batch):
                results = scraper.fetch_details(chunk)
                now = now_kst().isoformat()
                for sid, detail in results.items():
                    state = db.apply_detail(conn, source, sid, detail, now)
                    stats["details" if state == "open" else state] += 1
                conn.commit()
                scraper.pause()

        if complete:
            STATE.phase = "마감 확인"
            limit = min(settings.verify_limit, scraper.max_verify or settings.verify_limit)
            unseen = db.open_ids_not_seen(conn, source, started, limit)
            log.info("[%s] verifying %d postings missing from the listing…", source, len(unseen))
            for chunk in _chunks(unseen, scraper.detail_batch):
                results = scraper.fetch_details(chunk)
                now = now_kst().isoformat()
                for sid, detail in results.items():
                    stats["verified"] += 1
                    if detail.state == "unknown" and detail.reason == NO_RESPONSE:
                        closed = False  # blocked or offline: says nothing about the posting, check again next run
                    elif detail.state == "unknown":
                        closed = db.bump_missing(conn, source, sid, settings.missing_runs_to_close)
                    else:
                        closed = db.apply_detail(conn, source, sid, detail, now) == "closed"
                    stats["closed"] += closed
                conn.commit()
                scraper.pause()
        else:
            status = "partial"
    except Exception as e:  # noqa: BLE001 - one broken site must not stop the others
        conn.commit()
        status = "partial" if stats["listed"] else "failed"
        error = f"{type(e).__name__}: {e}"
        log.exception("[%s] scrape failed", source)
    finally:
        db.finish_run(conn, run_id, status, stats, now_kst().isoformat(), error)
    log.info("[%s] %s: %s", source, status, dict(stats))
    return {"source": source, "status": status, "error": error, **stats}


def start_background_scrape(settings: Settings, sources: Iterable[str] | None = None) -> bool:
    """Kick off a scrape in a thread; False if one is already running."""
    if STATE.running:
        return False

    def target() -> None:
        try:
            run_scrape(settings, sources)
        except AlreadyRunning:
            log.info("scrape skipped: another run holds the lock")
        except Exception:  # noqa: BLE001
            log.exception("background scrape failed")

    threading.Thread(target=target, name="jdc-scrape", daemon=True).start()
    return True
