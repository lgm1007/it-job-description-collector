import os

import psycopg
import pytest

from jdc import db, sync
from jdc.config import Settings
from jdc.models import Posting

TODAY = "2026-11-03"
NOW = "2026-11-03T06:00:00+09:00"


def make_posting(source_id: str = "1", **overrides) -> Posting:
    values = dict(
        source="wanted", source_id=source_id, url=f"https://example.test/{source_id}",
        title=f"백엔드 개발자 {source_id}", company="테스트컴퍼니", locations=["서울 강남구"],
        career_min=0, career_max=None, skills=["Kotlin", "Spring"], posted_at="2026-11-01",
    )
    values.update(overrides)
    return Posting(**values)


@pytest.fixture
def conn():
    connection = db.connect(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path, sources=("wanted",), chrome_path=None, cdp_port=9333, headless=True, close_browser=True,
        request_delay=0, detail_concurrency=1, max_details=100, verify_limit=100,
    )


def freeze_today(pg, day: str) -> None:
    """Rolled back with the rest of the test's transaction."""
    pg.execute(f"CREATE OR REPLACE FUNCTION private.today_kst() RETURNS date LANGUAGE sql STABLE AS $$ SELECT date '{day}' $$")


@pytest.fixture
def pg():
    """The real schema in a local Supabase database, emptied inside a transaction that is rolled back."""
    url = os.environ.get("JDC_TEST_DB_URL")
    if not url:
        pytest.skip("JDC_TEST_DB_URL이 없어 Postgres 테스트를 건너뜁니다 (README의 '개발' 참고)")
    connection = psycopg.connect(url, prepare_threshold=None)
    connection.execute("DELETE FROM public.jobs")
    connection.execute("DELETE FROM public.scrape_runs")
    connection.execute("DELETE FROM public.sync_state")
    freeze_today(connection, TODAY)
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def load(pg, conn):
    """Store postings the way a scrape does, then upload them."""

    def _load(*postings, seeding: bool = False) -> None:
        for posting in postings:
            db.upsert_listing(conn, posting, NOW, TODAY, seeding=seeding)
        sync.push(conn, pg, TODAY, NOW)

    return _load
