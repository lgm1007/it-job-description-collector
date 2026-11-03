import pytest

from jdc import db
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
        data_dir=tmp_path, host="127.0.0.1", port=8000, scrape_time="06:00", scrape_on_start=False,
        sources=("wanted",), chrome_path=None, cdp_port=9333, headless=True, close_browser=True,
        request_delay=0, detail_concurrency=1, max_details=100, verify_limit=100,
    )
