import pytest
from conftest import make_posting
from fastapi.testclient import TestClient

from jdc import api, db
from jdc.normalize import now_kst, today_kst


@pytest.fixture
def client(settings, monkeypatch):
    conn = db.connect(settings.db_path)
    now, today = now_kst().isoformat(), today_kst()
    db.upsert_listing(conn, make_posting("1", title="Kotlin 서버 개발자", posted_at=today), now, today)
    db.upsert_listing(conn, make_posting("2", source="jumpit", title="프론트엔드", locations=["경기 성남시"],
                                         skills=["React"]), now, today)
    conn.commit()
    conn.close()
    monkeypatch.setattr(api, "start_background_scrape", lambda settings, sources=None: True)
    with TestClient(api.create_app(settings, scheduler=False)) as c:
        yield c


def test_jobs_endpoint_filters(client):
    body = client.get("/api/jobs").json()
    assert body["total"] == 2
    assert client.get("/api/jobs", params={"q": "react"}).json()["total"] == 1
    assert client.get("/api/jobs", params={"region": "경기,부산"}).json()["total"] == 1
    assert client.get("/api/jobs", params=[("source", "jumpit"), ("source", "remember")]).json()["total"] == 1
    assert client.get("/api/jobs", params={"years": 99}).status_code == 422


def test_job_detail_and_meta(client):
    job_id = client.get("/api/jobs", params={"q": "kotlin"}).json()["items"][0]["id"]
    assert client.get(f"/api/jobs/{job_id}").json()["title"] == "Kotlin 서버 개발자"
    assert client.get("/api/jobs/999").status_code == 404
    meta = client.get("/api/meta").json()
    assert meta["total"] == 2 and meta["today"] == today_kst()
    assert [s["key"] for s in meta["sources"]] == ["wanted"]  # only configured sources


def test_scrape_trigger_and_ui(client):
    assert client.post("/api/scrape").status_code == 202
    page = client.get("/")
    assert page.status_code == 200 and "<html" in page.text
