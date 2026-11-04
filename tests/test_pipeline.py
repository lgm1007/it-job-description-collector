"""A scrape run's closed-posting logic, with the browser and the site faked out."""
from datetime import datetime, timedelta

import pytest
from conftest import make_posting

from jdc import db, pipeline
from jdc.models import Detail
from jdc.normalize import KST
from jdc.scrapers.base import Scraper


class FakeTab:
    def close(self):
        pass


class FakeBrowser:
    def open(self, url):
        return FakeTab()


class FakeScraper(Scraper):
    source = "wanted"
    label = "가짜"
    home_url = "https://example.test/"
    listing: list[str] = []
    complete = True
    details: dict[str, Detail] = {}
    asked: list[str] = []
    error: Exception | None = None

    def prepare(self):
        pass

    def pause(self):
        pass

    def iter_listing(self):
        if FakeScraper.error:
            raise FakeScraper.error
        yield [make_posting(sid) for sid in FakeScraper.listing]
        self.listing_complete = FakeScraper.complete

    def fetch_details(self, source_ids):
        FakeScraper.asked.extend(source_ids)
        return {sid: FakeScraper.details.get(sid, Detail("open")) for sid in source_ids}


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 3, 6, 0, tzinfo=KST)

    def __call__(self):
        self.t += timedelta(minutes=1)
        return self.t


@pytest.fixture
def fake(monkeypatch):
    FakeScraper.listing, FakeScraper.complete, FakeScraper.details = [], True, {}
    FakeScraper.asked, FakeScraper.error = [], None
    monkeypatch.setitem(pipeline.SCRAPERS, "wanted", FakeScraper)
    monkeypatch.setattr(pipeline, "now_kst", Clock())
    monkeypatch.setattr(pipeline, "today_kst", lambda: "2026-11-03")
    return FakeScraper


def run(conn, settings, listing, **kwargs):
    FakeScraper.listing = listing
    for key, value in kwargs.items():
        setattr(FakeScraper, key, value)
    FakeScraper.asked = []
    return pipeline.run_source(conn, FakeBrowser(), "wanted", settings)


def stored(conn):
    return sorted(r["source_id"] for r in conn.execute("SELECT source_id FROM jobs"))


def test_new_postings_get_details(conn, settings, fake):
    summary = run(conn, settings, ["1", "2"])
    assert summary["status"] == "ok" and summary["new"] == 2 and summary["details"] == 2
    assert sorted(fake.asked) == ["1", "2"]


def test_posting_missing_from_listing_is_checked_and_deleted(conn, settings, fake):
    run(conn, settings, ["1", "2", "3"])
    summary = run(conn, settings, ["1", "2"], details={"3": Detail("missing", reason="not_found")})
    assert fake.asked == ["3"]
    assert summary["closed"] == 1
    assert stored(conn) == ["1", "2"]


def test_unlisted_but_still_open_on_the_site_stays(conn, settings, fake):
    run(conn, settings, ["1", "2"])
    run(conn, settings, ["1"])
    assert stored(conn) == ["1", "2"]


def test_incomplete_listing_closes_nothing(conn, settings, fake):
    run(conn, settings, ["1", "2", "3"])
    summary = run(conn, settings, ["1"], complete=False, details={"2": Detail("missing"), "3": Detail("missing")})
    assert summary["status"] == "partial"
    assert fake.asked == []
    assert stored(conn) == ["1", "2", "3"]


def test_inconclusive_checks_delete_after_threshold(conn, settings, fake):
    run(conn, settings, ["1", "2"])
    for expected in (["1", "2"], ["1", "2"], ["1"]):
        run(conn, settings, ["1"], details={"2": Detail("unknown")})
        assert stored(conn) == expected


def test_blocked_checks_never_delete(conn, settings, fake):
    run(conn, settings, ["1", "2"])
    for _ in range(5):
        run(conn, settings, ["1"], details={"2": Detail("unknown", reason=pipeline.NO_RESPONSE)})
    assert stored(conn) == ["1", "2"]


def test_listing_that_suddenly_shrinks_skips_the_sweep(conn, settings, fake):
    run(conn, settings, [str(i) for i in range(60)])
    summary = run(conn, settings, [str(i) for i in range(10)], details={str(i): Detail("missing") for i in range(60)})
    assert summary["status"] == "partial"
    assert len(stored(conn)) == 60


def test_scraper_error_is_recorded(conn, settings, fake):
    summary = run(conn, settings, [], error=RuntimeError("사이트 구조 변경"))
    assert summary["status"] == "failed" and "사이트 구조 변경" in summary["error"]
    assert db.latest_runs(conn)[0]["status"] == "failed"


def test_scrape_lock_is_exclusive(tmp_path):
    path = tmp_path / "scrape.lock"
    with pipeline.ScrapeLock(path) as first:
        with pipeline.ScrapeLock(path) as second:
            assert first is True and second is False
    with pipeline.ScrapeLock(path) as again:
        assert again is True
