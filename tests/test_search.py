"""The Postgres functions the web app calls, against the real schema (see the `pg` fixture)."""
import json
import uuid

import psycopg
import pytest
from conftest import TODAY, freeze_today, make_posting

from jdc import sync


def call(pg, **kwargs):
    args = {f"p_{key}": value for key, value in kwargs.items()}
    placeholders = ", ".join(f"{key} => %({key})s" for key in args)
    return pg.execute(f"SELECT public.search_jobs({placeholders})", args).fetchone()[0]


def ids(result):
    return [item["url"].rsplit("/", 1)[-1] for item in result["items"]]


def meta(pg):
    return pg.execute("SELECT public.jobs_meta()").fetchone()[0]


def test_new_posting_is_searchable(pg, load):
    load(make_posting("1"))
    result = call(pg)
    assert result["total"] == 1
    item = result["items"][0]
    assert item["location"] == "서울 강남구"
    assert item["skills"] == ["Kotlin", "Spring"]
    assert item["career"] == "경력무관" and item["days_left"] is None


def test_keyword_filters(pg, load):
    load(
        make_posting("kotlin", title="서버 개발자", skills=["Kotlin", "Spring"]),
        make_posting("js", title="웹 프론트엔드", skills=["JavaScript", "React"]),
        make_posting("java", title="자바 개발자 (SI)", skills=["Java"], description="Spring 기반 SI 프로젝트"),
    )
    assert ids(call(pg, q="java")) == ["java"]  # not javascript
    assert ids(call(pg, q="JavaScript react")) == ["js"]  # every term must match
    assert ids(call(pg, q="spring", title_only=True)) == ["kotlin"]  # the other mentions it only in the body
    assert sorted(ids(call(pg, q="spring"))) == ["java", "kotlin"]
    assert sorted(ids(call(pg, exclude="si"))) == ["js", "kotlin"]
    assert ids(call(pg, q="개발자", exclude="(si)")) == ["kotlin"]
    assert call(pg, q="100%")["total"] == 0  # LIKE wildcards are escaped


def test_short_terms_match_whole_words(pg, load):
    load(
        make_posting("go", title="Go 서버 개발자", skills=[]),
        make_posting("google", title="Google 광고 개발자", skills=[]),
        make_posting("ai", title="생성형AI 엔지니어", skills=[]),
        make_posting("email", title="email 마케팅 개발자", skills=[]),
        make_posting("cpp", title="C++ 개발자", skills=[]),
        make_posting("c", title="C 개발자", skills=[]),
    )
    assert ids(call(pg, q="go")) == ["go"]
    assert ids(call(pg, q="ai")) == ["ai"]
    assert ids(call(pg, q="c")) == ["c"]  # not c++
    assert ids(call(pg, q="c++")) == ["cpp"]


def test_region_district_career_source_filters(pg, load):
    load(
        make_posting("seoul", career_min=3, career_max=None),
        make_posting("pangyo", locations=["경기 성남시 분당구"], career_min=0, career_max=0),
        make_posting("both", source="jumpit", locations=["서울 마포구", "부산 해운대구"], career_min=1, career_max=5),
        make_posting("unknown", locations=[], career_min=None, career_max=None),
    )
    assert sorted(ids(call(pg, regions=["서울"]))) == ["both", "seoul"]
    assert sorted(ids(call(pg, regions=["경기", "부산"]))) == ["both", "pangyo"]
    assert ids(call(pg, districts=["경기 성남시"])) == ["pangyo"]
    assert sorted(ids(call(pg, years=0))) == ["pangyo", "unknown"]
    assert sorted(ids(call(pg, years=3))) == ["both", "seoul", "unknown"]
    assert sorted(ids(call(pg, years=10))) == ["seoul", "unknown"]
    assert ids(call(pg, sources=["jumpit"])) == ["both"]
    assert call(pg, regions=[], districts=[], sources=[])["total"] == 4  # empty means no filter


def test_days_filter_and_sorting(pg, load):
    load(
        make_posting("old", posted_at="2026-10-01", deadline="2026-11-05"),
        make_posting("fresh", posted_at="2026-11-03", deadline=None),
        make_posting("mid", posted_at="2026-10-20", deadline="2026-11-20"),
    )
    assert ids(call(pg)) == ["fresh", "mid", "old"]
    assert ids(call(pg, sort="deadline")) == ["old", "mid", "fresh"]
    assert ids(call(pg, days=3)) == ["fresh"]
    items = call(pg)["items"]
    assert items[0]["is_new"] is True and items[1]["is_new"] is False
    assert items[2]["days_left"] == 2 and items[2]["deadline"] == "2026-11-05"


def test_same_posting_on_two_sites_is_collapsed(pg, load):
    load(
        make_posting("jk1", source="jobkorea", company="㈜버즈빌", title="[광고] 백엔드"),
        make_posting("w1", source="wanted", company="버즈빌", title="[광고]백엔드"),
        make_posting("other"),
    )
    result = call(pg)
    assert result["total"] == 2
    collapsed = next(i for i in result["items"] if i["company"] == "버즈빌")
    assert collapsed["source"] == "wanted"  # preferred copy
    assert [o["source"] for o in collapsed["also_on"]] == ["jobkorea"]
    assert call(pg, dedupe=False)["total"] == 3
    assert all(item["also_on"] == [] for item in call(pg, dedupe=False)["items"])
    # Filtered down to the other site, that site's copy stands in.
    assert [i["source"] for i in call(pg, sources=["jobkorea"])["items"]] == ["jobkorea"]


def test_first_run_backlog_without_dates_is_not_new(pg, load):
    load(make_posting("backlog", posted_at=None), make_posting("dated", posted_at="2026-10-20"), seeding=True)
    load(make_posting("later", posted_at=None))
    items = call(pg)["items"]
    assert [i["url"].rsplit("/", 1)[-1] for i in items] == ["later", "dated", "backlog"]
    backlog = items[-1]
    assert backlog["listed_at"] is None and backlog["is_new"] is False
    assert items[0]["listed_at"] == TODAY and items[0]["is_new"] is True
    assert ids(call(pg, days=3)) == ["later"]


def test_pagination(pg, load):
    load(*[make_posting(str(i), posted_at=f"2026-11-0{i + 1}") for i in range(3)],
         *[make_posting(str(i), posted_at="2026-10-01") for i in range(3, 5)])
    page2 = call(pg, page=2, size=2)
    assert page2["total"] == 5 and page2["page"] == 2 and page2["size"] == 2
    assert ids(page2) == ["0", "4"]
    assert call(pg, page=9, size=2)["items"] == []
    assert call(pg, size=1000)["size"] == 100


def test_past_deadlines_are_hidden_between_scrapes(pg, load):
    load(make_posting("1"), make_posting("today", deadline=TODAY),
         make_posting("w", company="버즈빌", title="백엔드"),
         make_posting("jk", source="jobkorea", company="버즈빌", title="백엔드", deadline=TODAY))
    assert call(pg)["total"] == 3
    freeze_today(pg, "2026-11-04")
    result = call(pg)
    assert sorted(ids(result)) == ["1", "w"]
    assert all(item["also_on"] == [] for item in result["items"])  # nor offered as another copy
    assert meta(pg)["total"] == 2


def test_meta_counts(pg, load):
    load(make_posting("1"), make_posting("2", source="jumpit", locations=["경기 성남시"]),
         make_posting("3", is_open=False))
    m = meta(pg)
    assert m["total"] == 2 and m["unique_total"] == 2
    assert m["sources"] == {"wanted": 1, "jumpit": 1}
    assert {r["name"] for r in m["regions"]} == {"서울", "경기"}
    assert m["districts"]["경기"] == [{"name": "경기 성남시", "count": 1}]
    assert m["synced_at"] is not None


def test_meta_on_an_empty_database(pg):
    m = meta(pg)
    assert m["total"] == 0 and m["sources"] == {} and m["regions"] == [] and m["districts"] == {}
    assert m["runs"] == [] and m["synced_at"] is None


# -- who can read --------------------------------------------------------------------------

def make_account(pg) -> tuple[str, str]:
    user_id, email = str(uuid.uuid4()), f"{uuid.uuid4().hex}@example.test"
    pg.execute("INSERT INTO auth.users (id, email) VALUES (%s, %s)", (user_id, email))
    return user_id, email


def become(pg, role: str, user_id: str | None = None) -> None:
    pg.execute(f"SET LOCAL ROLE {role}")
    claims = {"role": role, **({"sub": user_id} if user_id else {})}
    pg.execute("SELECT set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))


@pytest.mark.parametrize("statement", [
    "SELECT count(*) FROM public.jobs",
    "SELECT count(*) FROM public.scrape_runs",
    "SELECT public.search_jobs()",
    "SELECT public.jobs_meta()",
    "SELECT count(*) FROM private.viewers",
])
def test_anonymous_callers_get_nothing(pg, load, statement):
    load(make_posting("1"))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), pg.transaction():
        become(pg, "anon")
        pg.execute(statement)


def test_signed_in_account_off_the_allow_list_sees_nothing(pg, load):
    load(make_posting("1"))
    user_id, _ = make_account(pg)
    become(pg, "authenticated", user_id)
    assert pg.execute("SELECT count(*) FROM public.jobs").fetchone()[0] == 0
    assert call(pg)["total"] == 0
    m = meta(pg)
    assert m["viewer"] is False and m["total"] == 0 and m["runs"] == [] and m["synced_at"] is None


def test_allowed_account_reads_but_cannot_write(pg, load):
    load(make_posting("1"))
    user_id, email = make_account(pg)
    assert sync.add_viewer(pg, email) is True
    assert sync.add_viewer(pg, email) is True  # adding twice is fine
    assert sync.add_viewer(pg, "nobody@example.test") is False
    become(pg, "authenticated", user_id)
    assert call(pg)["total"] == 1
    assert meta(pg)["viewer"] is True
    job_id = pg.execute("SELECT id FROM public.jobs").fetchone()[0]
    for statement in ("DELETE FROM public.jobs", "UPDATE public.jobs SET title = 'x'",
                      "INSERT INTO public.sync_state (synced_at) VALUES (now())",
                      "INSERT INTO private.viewers (user_id) SELECT gen_random_uuid()"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), pg.transaction():
            pg.execute(statement)
    assert pg.execute("SELECT title FROM public.jobs WHERE id = %s", (job_id,)).fetchone()[0] != "x"
