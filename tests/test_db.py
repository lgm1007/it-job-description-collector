from conftest import NOW, TODAY, make_posting

from jdc import db
from jdc.models import Detail


def stored(conn):
    return sorted(r[0] for r in conn.execute("SELECT source_id FROM jobs"))


def row(conn, source_id="1"):
    return conn.execute("SELECT * FROM jobs WHERE source_id = ?", (source_id,)).fetchone()


def test_new_posting_is_stored_with_derived_fields(conn):
    assert db.upsert_listing(conn, make_posting("1"), NOW, TODAY) == "new"
    job = row(conn)
    assert job["location_text"] == "서울 강남구" and job["regions"] == "|서울|" and job["districts"] == "|서울 강남구|"
    assert "kotlin" in job["title_text"] and "kotlin" in job["search_text"]


def test_closed_and_expired_postings_are_not_stored(conn):
    assert db.upsert_listing(conn, make_posting("open"), NOW, TODAY) == "new"
    assert db.upsert_listing(conn, make_posting("closed", is_open=False), NOW, TODAY) == "skipped"
    assert db.upsert_listing(conn, make_posting("expired", deadline="2026-11-02"), NOW, TODAY) == "skipped"
    db.upsert_listing(conn, make_posting("today", deadline=TODAY), NOW, TODAY)
    assert stored(conn) == ["open", "today"]
    assert db.delete_expired(conn, "2026-11-04") == 1
    assert stored(conn) == ["open"]


def test_listing_that_marks_a_posting_closed_deletes_it(conn):
    db.upsert_listing(conn, make_posting("1", deadline="2026-11-30"), NOW, TODAY)
    db.upsert_listing(conn, make_posting("2"), NOW, TODAY)
    assert db.upsert_listing(conn, make_posting("1", deadline="2026-11-02"), NOW, TODAY) == "closed"
    assert db.upsert_listing(conn, make_posting("2", is_open=False), NOW, TODAY) == "closed"
    assert stored(conn) == []


def test_deleted_posting_listed_again_comes_back_as_new(conn):
    db.upsert_listing(conn, make_posting("1", deadline="2026-11-02"), NOW, "2026-11-01")
    db.delete_expired(conn, TODAY)
    assert db.upsert_listing(conn, make_posting("1", deadline="2026-11-30"), NOW, TODAY) == "new"
    assert stored(conn) == ["1"]


def test_detail_merges_without_being_overwritten_by_listing(conn):
    db.upsert_listing(conn, make_posting("1", locations=["서울"], skills=[]), NOW, TODAY)
    db.apply_detail(conn, "wanted", "1", Detail("open", {
        "description": "[자격요건]\nKafka 운영 경험", "posted_at": "2026-10-30",
        "locations": ["서울특별시 송파구 석촌호수로 272"], "skills": ["Kafka"],
    }), NOW)
    # The next listing pass carries less information than the detail page did.
    db.upsert_listing(conn, make_posting("1", locations=["서울"], skills=[], posted_at=None), NOW, TODAY)
    job = row(conn)
    assert job["description"].endswith("Kafka 운영 경험")
    assert job["posted_at"] == "2026-10-30"
    assert job["location_text"] == "서울 송파구"
    assert job["skills"] == '["Kafka"]'
    assert "kafka" in job["search_text"]


def test_unparseable_detail_address_does_not_replace_region(conn):
    db.upsert_listing(conn, make_posting("1", locations=["서울"]), NOW, TODAY)
    db.apply_detail(conn, "wanted", "1", Detail("open", {"locations": ["본사 3층 (엘리베이터 옆)"]}), NOW)
    assert row(conn)["location_text"] == "서울"


def test_detail_closed_or_missing_deletes(conn):
    db.upsert_listing(conn, make_posting("1"), NOW, TODAY)
    db.upsert_listing(conn, make_posting("2"), NOW, TODAY)
    db.upsert_listing(conn, make_posting("3"), NOW, TODAY)
    assert db.apply_detail(conn, "wanted", "1", Detail("closed", reason="status:close"), NOW) == "closed"
    assert db.apply_detail(conn, "wanted", "2", Detail("missing", reason="not_found"), NOW) == "closed"
    assert db.apply_detail(conn, "wanted", "3", Detail("unknown"), NOW) == "unknown"
    assert stored(conn) == ["3"]


def test_unlisted_bookkeeping(conn):
    db.upsert_listing(conn, make_posting("1"), "2026-11-01T06:00:00+09:00", TODAY)
    db.upsert_listing(conn, make_posting("2"), NOW, TODAY)
    assert db.open_ids_not_seen(conn, "wanted", "2026-11-03T00:00:00+09:00", 10) == ["1"]
    assert db.bump_missing(conn, "wanted", "1", 2) is False
    assert db.bump_missing(conn, "wanted", "1", 2) is True
    assert stored(conn) == ["2"]


def test_closed_rows_from_older_databases_are_purged(tmp_path):
    path = tmp_path / "old.sqlite3"
    legacy = db.sqlite3.connect(path)
    legacy.execute(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY, source TEXT, source_id TEXT, deadline TEXT, "
        "last_seen_at TEXT, dedupe_key TEXT, status TEXT NOT NULL DEFAULT 'open')"
    )
    legacy.executemany("INSERT INTO jobs (source, source_id, status) VALUES ('wanted', ?, ?)",
                       [("1", "open"), ("2", "closed")])
    legacy.commit()
    legacy.close()
    conn = db.connect(path)
    assert [r[0] for r in conn.execute("SELECT source_id FROM jobs")] == ["1"]
    conn.close()
