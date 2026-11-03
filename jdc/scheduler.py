"""Daily scrape schedule that lives inside the web server process."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db
from .config import Settings
from .normalize import KST, now_kst
from .pipeline import AlreadyRunning, run_scrape

log = logging.getLogger(__name__)


def _scheduled_run(settings: Settings) -> None:
    try:
        run_scrape(settings)
    except AlreadyRunning:
        log.info("scheduled scrape skipped: another run is in progress")
    except Exception:  # noqa: BLE001 - keep the scheduler alive
        log.exception("scheduled scrape failed")


def is_stale(settings: Settings, max_age: timedelta = timedelta(hours=24)) -> bool:
    conn = db.connect(settings.db_path)
    try:
        last = db.last_success_at(conn)
    finally:
        conn.close()
    return last is None or now_kst() - datetime.fromisoformat(last) > max_age


def start_scheduler(settings: Settings) -> BackgroundScheduler:
    hour, minute = (int(x) for x in settings.scrape_time.split(":"))
    scheduler = BackgroundScheduler(timezone=KST)
    scheduler.add_job(
        _scheduled_run, CronTrigger(hour=hour, minute=minute, timezone=KST), args=[settings],
        id="daily-scrape", max_instances=1, coalesce=True, misfire_grace_time=3600,
    )
    if settings.scrape_on_start and is_stale(settings):
        log.info("last successful scrape is older than a day; scraping now")
        scheduler.add_job(_scheduled_run, args=[settings], id="catch-up-scrape",
                          next_run_time=now_kst() + timedelta(seconds=5))
    scheduler.start()
    job = scheduler.get_job("daily-scrape")
    log.info("daily scrape scheduled at %s KST (next: %s)", settings.scrape_time, job.next_run_time)
    return scheduler
