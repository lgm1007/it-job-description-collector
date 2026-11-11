from conftest import NOW, TODAY, make_posting

import pytest

from jdc import db, sync


def row(conn, source_id="1"):
    return next(r for r in sync.local_rows(conn, TODAY) if r["source_id"] == source_id)


def remote_jobs(pg):
    return {r[0]: r[1] for r in pg.execute("SELECT source_id, title FROM public.jobs")}


def test_row_holds_what_the_viewer_needs(conn):
    db.upsert_listing(conn, make_posting("1", locations=["서울 강남구", "경기 성남시"], career_min=3, career_max=5), NOW, TODAY)
    r = row(conn)
    assert r["regions"] == ["서울", "경기"] and r["districts"] == ["서울 강남구", "경기 성남시"]
    assert r["location_text"] == "서울 강남구 외 1" and r["career"] == "3~5년"
    assert r["skills"] == ["Kotlin", "Spring"] and r["listed_at"] == "2026-11-01"
    assert set(r) == set(sync.COLUMNS)


def test_listed_date_falls_back_to_first_seen_except_for_a_first_run_backlog(conn):
    db.upsert_listing(conn, make_posting("later", posted_at=None), NOW, TODAY)
    db.upsert_listing(conn, make_posting("backlog", posted_at=None), NOW, TODAY, seeding=True)
    assert row(conn, "later")["listed_at"] == TODAY
    assert row(conn, "backlog")["listed_at"] is None


def test_expired_postings_are_not_uploaded(conn):
    db.upsert_listing(conn, make_posting("1", deadline=TODAY), NOW, TODAY)
    assert len(sync.local_rows(conn, TODAY)) == 1
    assert sync.local_rows(conn, "2026-11-04") == []


def test_values_postgres_would_reject_are_cleaned(conn):
    db.upsert_listing(conn, make_posting("1", title="백엔드\x00 개발자", description="본문\x00", skills=["Go\x00"]), NOW, TODAY)
    conn.execute("UPDATE jobs SET deadline = '상시', posted_at = '2026-13-45'")
    r = row(conn)
    assert r["title"] == "백엔드 개발자" and r["description"] == "본문" and r["skills"] == ["Go"]
    assert "\x00" not in r["search_text"]
    assert r["deadline"] is None and r["posted_at"] is None


def test_hash_ignores_bookkeeping_but_not_content(conn):
    db.upsert_listing(conn, make_posting("1"), NOW, TODAY)
    before = row(conn)["content_hash"]
    db.upsert_listing(conn, make_posting("1"), "2026-11-04T06:00:00+09:00", TODAY)  # seen again
    assert row(conn)["content_hash"] == before
    db.upsert_listing(conn, make_posting("1", title="바뀐 제목"), NOW, TODAY)
    assert row(conn)["content_hash"] != before


def test_only_changes_are_uploaded_and_ids_stay(conn, pg):
    db.upsert_listing(conn, make_posting("1"), NOW, TODAY)
    db.upsert_listing(conn, make_posting("2"), NOW, TODAY)
    assert sync.push(conn, pg, TODAY, NOW) == sync.SyncResult(uploaded=2, deleted=0, total=2)
    first_ids = dict(pg.execute("SELECT source_id, id FROM public.jobs").fetchall())
    assert sync.push(conn, pg, TODAY, NOW).uploaded == 0

    db.upsert_listing(conn, make_posting("2", title="바뀐 제목"), NOW, TODAY)
    db.upsert_listing(conn, make_posting("3"), NOW, TODAY)
    assert sync.push(conn, pg, TODAY, NOW) == sync.SyncResult(uploaded=2, deleted=0, total=3)
    assert remote_jobs(pg)["2"] == "바뀐 제목"
    ids = dict(pg.execute("SELECT source_id, id FROM public.jobs").fetchall())
    assert ids["1"] == first_ids["1"] and ids["2"] == first_ids["2"] and ids["3"] > ids["2"]


def test_postings_deleted_locally_are_deleted_upstream(conn, pg):
    db.upsert_listing(conn, make_posting("1"), NOW, TODAY)
    db.upsert_listing(conn, make_posting("2", source="jumpit"), NOW, TODAY)
    db.upsert_listing(conn, make_posting("2"), NOW, TODAY)  # same id on another site stays
    sync.push(conn, pg, TODAY, NOW)
    db.upsert_listing(conn, make_posting("2", source="jumpit", is_open=False), NOW, TODAY)
    assert sync.push(conn, pg, TODAY, NOW).deleted == 1
    assert sorted(pg.execute("SELECT source, source_id FROM public.jobs").fetchall()) == [("wanted", "1"), ("wanted", "2")]


def test_postings_past_their_deadline_are_deleted_upstream(conn, pg):
    db.upsert_listing(conn, make_posting("1", deadline=TODAY), NOW, TODAY)
    sync.push(conn, pg, TODAY, NOW)
    assert sync.push(conn, pg, "2026-11-04", NOW).deleted == 1
    assert remote_jobs(pg) == {}


def test_uploading_an_empty_local_database_is_refused_unless_forced(conn, pg, tmp_path):
    for i in range(60):
        db.upsert_listing(conn, make_posting(str(i)), NOW, TODAY)
    sync.push(conn, pg, TODAY, NOW)
    empty = db.connect(tmp_path / "empty.sqlite3")
    with pytest.raises(sync.SyncError, match="60건 중 60건"):
        sync.push(empty, pg, TODAY, NOW)
    assert len(remote_jobs(pg)) == 60  # untouched
    assert sync.push(empty, pg, TODAY, NOW, force=True).deleted == 60
    assert remote_jobs(pg) == {}
    empty.close()


def test_latest_runs_and_upload_time_are_mirrored(conn, pg):
    from collections import Counter

    old = db.start_run(conn, "wanted", "2026-11-02T06:00:00+09:00")
    db.finish_run(conn, old, "failed", Counter(), "2026-11-02T06:01:00+09:00", "터짐\x00")
    new = db.start_run(conn, "wanted", NOW)
    db.finish_run(conn, new, "ok", Counter(listed=5, new=2, closed=1), NOW)
    other = db.start_run(conn, "jumpit", NOW)
    db.finish_run(conn, other, "failed", Counter(), NOW, "터짐\x00")
    sync.push(conn, pg, TODAY, NOW)
    runs = pg.execute(
        "SELECT source, status, listed, added, closed, error FROM public.scrape_runs ORDER BY source"
    ).fetchall()
    assert runs == [("jumpit", "failed", 0, 0, 0, "터짐"), ("wanted", "ok", 5, 2, 1, None)]
    assert pg.execute("SELECT count(*) FROM public.sync_state").fetchone()[0] == 1
    sync.push(conn, pg, TODAY, "2026-11-04T06:00:00+09:00")
    assert pg.execute("SELECT count(*) FROM public.sync_state").fetchone()[0] == 1
    assert str(pg.execute("SELECT (synced_at at time zone 'Asia/Seoul')::date FROM public.sync_state").fetchone()[0]) == "2026-11-04"
