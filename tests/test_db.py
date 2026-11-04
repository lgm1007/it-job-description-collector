from conftest import NOW, TODAY, make_posting

from jdc import db
from jdc.models import Detail


def ids(result):
    return [item["url"].rsplit("/", 1)[-1] for item in result["items"]]


def search(conn, **kwargs):
    return db.search(conn, db.SearchFilter(**kwargs), TODAY)


def stored(conn):
    return sorted(r[0] for r in conn.execute("SELECT source_id FROM jobs"))


def test_new_posting_is_searchable(conn):
    assert db.upsert_listing(conn, make_posting("1"), NOW, TODAY) == "new"
    result = search(conn)
    assert result["total"] == 1
    item = result["items"][0]
    assert item["location"] == "서울 강남구" and item["regions"] == ["서울"]
    assert item["skills"] == ["Kotlin", "Spring"]


def test_closed_and_expired_postings_are_not_stored(conn):
    assert db.upsert_listing(conn, make_posting("open"), NOW, TODAY) == "new"
    assert db.upsert_listing(conn, make_posting("closed", is_open=False), NOW, TODAY) == "skipped"
    assert db.upsert_listing(conn, make_posting("expired", deadline="2026-11-02"), NOW, TODAY) == "skipped"
    db.upsert_listing(conn, make_posting("today", deadline=TODAY), NOW, TODAY)
    assert stored(conn) == ["open", "today"]
    assert sorted(ids(search(conn))) == ["open", "today"]
    # Between scrapes the deadline already hides it; the next scrape deletes it.
    assert ids(db.search(conn, db.SearchFilter(), "2026-11-04")) == ["open"]
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
    assert search(conn)["total"] == 1


def test_detail_merges_without_being_overwritten_by_listing(conn):
    db.upsert_listing(conn, make_posting("1", locations=["서울"], skills=[]), NOW, TODAY)
    db.apply_detail(conn, "wanted", "1", Detail("open", {
        "description": "[자격요건]\nKafka 운영 경험", "posted_at": "2026-10-30",
        "locations": ["서울특별시 송파구 석촌호수로 272"], "skills": ["Kafka"],
    }), NOW)
    # The next listing pass carries less information than the detail page did.
    db.upsert_listing(conn, make_posting("1", locations=["서울"], skills=[], posted_at=None), NOW, TODAY)
    job = db.get_job(conn, 1)
    assert job["description"].endswith("Kafka 운영 경험")
    assert job["posted_at"] == "2026-10-30"
    assert job["location"] == "서울 송파구"
    assert job["skills"] == ["Kafka"]
    assert ids(search(conn, q="kafka")) == ["1"]


def test_unparseable_detail_address_does_not_replace_region(conn):
    db.upsert_listing(conn, make_posting("1", locations=["서울"]), NOW, TODAY)
    db.apply_detail(conn, "wanted", "1", Detail("open", {"locations": ["본사 3층 (엘리베이터 옆)"]}), NOW)
    assert db.get_job(conn, 1)["location"] == "서울"


def test_detail_closed_or_missing_deletes(conn):
    db.upsert_listing(conn, make_posting("1"), NOW, TODAY)
    db.upsert_listing(conn, make_posting("2"), NOW, TODAY)
    db.upsert_listing(conn, make_posting("3"), NOW, TODAY)
    assert db.apply_detail(conn, "wanted", "1", Detail("closed", reason="status:close"), NOW) == "closed"
    assert db.apply_detail(conn, "wanted", "2", Detail("missing", reason="not_found"), NOW) == "closed"
    assert db.apply_detail(conn, "wanted", "3", Detail("unknown"), NOW) == "unknown"
    assert stored(conn) == ["3"]


def test_keyword_filters(conn):
    db.upsert_listing(conn, make_posting("kotlin", title="서버 개발자", skills=["Kotlin", "Spring"]), NOW, TODAY)
    db.upsert_listing(conn, make_posting("js", title="웹 프론트엔드", skills=["JavaScript", "React"]), NOW, TODAY)
    db.upsert_listing(conn, make_posting("java", title="자바 개발자 (SI)", skills=["Java"],
                                         description="Spring 기반 SI 프로젝트"), NOW, TODAY)
    assert ids(search(conn, q="java")) == ["java"]  # not javascript
    assert ids(search(conn, q="JavaScript react")) == ["js"]  # every term must match
    assert ids(search(conn, q="spring", title_only=True)) == ["kotlin"]  # the other mentions it only in the body
    assert sorted(ids(search(conn, q="spring"))) == ["java", "kotlin"]
    assert sorted(ids(search(conn, exclude="si"))) == ["js", "kotlin"]
    assert ids(search(conn, q="개발자", exclude="(si)")) == ["kotlin"]
    assert search(conn, q="100%")["total"] == 0  # LIKE wildcards are escaped


def test_region_district_career_source_filters(conn):
    db.upsert_listing(conn, make_posting("seoul", career_min=3, career_max=None), NOW, TODAY)
    db.upsert_listing(conn, make_posting("pangyo", locations=["경기 성남시 분당구"], career_min=0, career_max=0),
                      NOW, TODAY)
    db.upsert_listing(conn, make_posting("both", source="jumpit", locations=["서울 마포구", "부산 해운대구"],
                                         career_min=1, career_max=5), NOW, TODAY)
    db.upsert_listing(conn, make_posting("unknown", locations=[], career_min=None, career_max=None), NOW, TODAY)
    assert sorted(ids(search(conn, regions=["서울"]))) == ["both", "seoul"]
    assert sorted(ids(search(conn, regions=["경기", "부산"]))) == ["both", "pangyo"]
    assert ids(search(conn, districts=["경기 성남시"])) == ["pangyo"]
    assert sorted(ids(search(conn, years=0))) == ["pangyo", "unknown"]
    assert sorted(ids(search(conn, years=3))) == ["both", "seoul", "unknown"]
    assert sorted(ids(search(conn, years=10))) == ["seoul", "unknown"]
    assert ids(search(conn, sources=["jumpit"])) == ["both"]


def test_days_filter_and_sorting(conn):
    db.upsert_listing(conn, make_posting("old", posted_at="2026-10-01", deadline="2026-11-05"), NOW, TODAY)
    db.upsert_listing(conn, make_posting("fresh", posted_at="2026-11-03", deadline=None), NOW, TODAY)
    db.upsert_listing(conn, make_posting("mid", posted_at="2026-10-20", deadline="2026-11-20"), NOW, TODAY)
    assert ids(search(conn)) == ["fresh", "mid", "old"]
    assert ids(search(conn, sort="deadline")) == ["old", "mid", "fresh"]
    assert ids(search(conn, days=3)) == ["fresh"]
    assert search(conn)["items"][0]["is_new"] is True


def test_same_posting_on_two_sites_is_collapsed(conn):
    db.upsert_listing(conn, make_posting("jk1", source="jobkorea", company="㈜버즈빌", title="[광고] 백엔드"),
                      NOW, TODAY)
    db.upsert_listing(conn, make_posting("w1", source="wanted", company="버즈빌", title="[광고]백엔드"), NOW, TODAY)
    db.upsert_listing(conn, make_posting("other"), NOW, TODAY)
    result = search(conn)
    assert result["total"] == 2
    collapsed = next(i for i in result["items"] if i["company"] == "버즈빌")
    assert collapsed["source"] == "wanted"  # preferred copy
    assert [o["source"] for o in collapsed["also_on"]] == ["jobkorea"]
    assert search(conn, dedupe=False)["total"] == 3


def test_first_run_backlog_without_dates_is_not_new(conn):
    db.upsert_listing(conn, make_posting("backlog", posted_at=None), NOW, TODAY, seeding=True)
    db.upsert_listing(conn, make_posting("later", posted_at=None), NOW, TODAY)
    db.upsert_listing(conn, make_posting("dated", posted_at="2026-10-20"), NOW, TODAY, seeding=True)
    items = search(conn)["items"]
    assert [i["url"].rsplit("/", 1)[-1] for i in items] == ["later", "dated", "backlog"]
    backlog = items[-1]
    assert backlog["listed_at"] is None and backlog["is_new"] is False
    assert items[0]["listed_at"] == TODAY and items[0]["is_new"] is True
    assert ids(search(conn, days=3)) == ["later"]


def test_pagination(conn):
    for i in range(5):
        db.upsert_listing(conn, make_posting(str(i), posted_at=f"2026-11-0{i + 1}"), NOW, TODAY)
    page2 = search(conn, page=2, size=2)
    assert page2["total"] == 5 and ids(page2) == ["2", "1"]


def test_unlisted_bookkeeping(conn):
    db.upsert_listing(conn, make_posting("1"), "2026-11-01T06:00:00+09:00", TODAY)
    db.upsert_listing(conn, make_posting("2"), NOW, TODAY)
    assert db.open_ids_not_seen(conn, "wanted", "2026-11-03T00:00:00+09:00", 10) == ["1"]
    assert db.bump_missing(conn, "wanted", "1", 2) is False
    assert db.bump_missing(conn, "wanted", "1", 2) is True
    assert ids(search(conn)) == ["2"]


def test_facets(conn):
    db.upsert_listing(conn, make_posting("1"), NOW, TODAY)
    db.upsert_listing(conn, make_posting("2", source="jumpit", locations=["경기 성남시"]), NOW, TODAY)
    db.upsert_listing(conn, make_posting("3", is_open=False), NOW, TODAY)
    f = db.facets(conn, TODAY)
    assert f["total"] == 2 and f["sources"] == {"wanted": 1, "jumpit": 1}
    assert {r["name"] for r in f["regions"]} == {"서울", "경기"}
    assert f["districts"]["경기"] == [{"name": "경기 성남시", "count": 1}]


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
