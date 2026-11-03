"""HTTP API plus the static web UI."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from . import db
from .config import PROJECT_ROOT, Settings, load_settings
from .normalize import REGIONS, today_kst
from .pipeline import STATE, start_background_scrape
from .scrapers import SOURCE_LABELS

log = logging.getLogger(__name__)
WEB_DIR = PROJECT_ROOT / "web"


def _split(values: list[str]) -> list[str]:
    """Accept both ?region=서울&region=경기 and ?region=서울,경기."""
    return [v.strip() for value in values for v in value.split(",") if v.strip()]


def create_app(settings: Settings | None = None, *, scheduler: bool = True) -> FastAPI:
    settings = settings or load_settings()
    db.connect(settings.db_path).close()  # create the schema up front

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        sched = None
        if scheduler:
            from .scheduler import start_scheduler

            sched = start_scheduler(settings)
        app.state.scheduler = sched
        yield
        if sched is not None:
            sched.shutdown(wait=False)

    app = FastAPI(title="개발자 채용공고 모아보기", lifespan=lifespan)

    @app.middleware("http")
    async def revalidate_ui(request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-cache")  # pick up UI changes on reload
        return response

    @contextmanager
    def connection():
        conn = db.connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    @app.get("/api/jobs")
    def list_jobs(
        q: str | None = None,
        exclude: str | None = None,
        title_only: bool = False,
        region: list[str] = Query(default=[]),
        district: list[str] = Query(default=[]),
        years: int | None = Query(default=None, ge=0, le=30),
        source: list[str] = Query(default=[]),
        days: int | None = Query(default=None, ge=1, le=90),
        sort: Literal["latest", "deadline"] = "latest",
        dedupe: bool = True,
        page: int = Query(default=1, ge=1),
        size: int = Query(default=30, ge=1, le=100),
    ):
        sources = [s for s in _split(source) if s in SOURCE_LABELS]
        f = db.SearchFilter(
            q=q, exclude=exclude, title_only=title_only, regions=_split(region), districts=_split(district),
            years=years, sources=sources, days=days, sort=sort, dedupe=dedupe, page=page, size=size,
        )
        with connection() as conn:
            return db.search(conn, f, today_kst())

    @app.get("/api/jobs/{job_id}")
    def job_detail(job_id: int):
        with connection() as conn:
            job = db.get_job(conn, job_id, today_kst())
        if job is None:
            raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")
        return job

    @app.get("/api/meta")
    def meta():
        today = today_kst()
        with connection() as conn:
            counts = db.facets(conn, today)
            runs = db.latest_runs(conn)
        job = app.state.scheduler.get_job("daily-scrape") if getattr(app.state, "scheduler", None) else None
        scrape = asdict(STATE)
        if not scrape["running"]:  # a `jdc scrape` started from the command line
            active = next((r for r in runs if r["status"] == "running"), None)
            if active:
                scrape.update(running=True, source=active["source"], phase=None)
        return {
            "today": today,
            "sources": [{"key": k, "label": v, "count": counts["sources"].get(k, 0)} for k, v in SOURCE_LABELS.items()
                        if k in settings.sources],
            "region_order": list(REGIONS),
            "regions": counts["regions"],
            "districts": counts["districts"],
            "total": counts["total"],
            "unique_total": counts["unique_total"],
            "runs": runs,
            "scrape": scrape,
            "next_scrape_at": job.next_run_time.isoformat() if job and job.next_run_time else None,
            "scrape_time": settings.scrape_time,
        }

    @app.get("/api/runs")
    def runs(limit: int = Query(default=30, ge=1, le=200)):
        with connection() as conn:
            return db.recent_runs(conn, limit)

    @app.post("/api/scrape", status_code=202)
    def scrape(source: list[str] = Query(default=[])):
        sources = [s for s in _split(source) if s in settings.sources] or None
        if not start_background_scrape(settings, sources):
            raise HTTPException(status_code=409, detail="이미 수집 중입니다")
        return {"started": True}

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
