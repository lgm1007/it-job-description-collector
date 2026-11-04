"""Parsers against trimmed-down payloads shaped like each site's real responses."""
from datetime import date

from jdc.scrapers import jobkorea, jobplanet, jumpit, remember, saramin, wanted

TODAY = date(2026, 11, 3)


def test_wanted_list_item():
    p = wanted.parse_list_item({
        "id": 396362, "status": "active", "hidden": False, "position": "[ICT] 구매시스템 구축 담당자",
        "company": {"name": "한화그룹 (Hanwha)"}, "annual_from": 3, "annual_to": 100, "due_time": "2026-11-15",
        "address": {"location": "서울", "district": "중구", "full_location": "을지로 100"},
        "title_img": {"thumb": "https://img/t.png"},
    })
    assert (p.source_id, p.url) == ("396362", "https://www.wanted.co.kr/wd/396362")
    assert p.locations == ["서울 중구"]
    assert (p.career_min, p.career_max) == (3, None)
    assert p.deadline == "2026-11-15" and p.is_open


def test_wanted_detail_and_closed_detail():
    d = wanted.parse_detail({
        "status": "active", "hidden": False, "confirm_time": "2026-11-03", "due_time": None,
        "employment_type": "regular", "main_tasks": "API 개발", "requirements": "Kotlin 3년",
        "category_tag": {"child_tags": [{"text": "서버 개발자"}]},
    })
    assert d.state == "open"
    assert d.fields["posted_at"] == "2026-11-03" and d.fields["deadline"] is None
    assert d.fields["employment_type"] == "정규직" and d.fields["categories"] == ["서버 개발자"]
    assert "[주요업무]\nAPI 개발" in d.fields["description"]
    assert wanted.parse_detail({"status": "close", "hidden": False}).state == "closed"


def test_jumpit_list_item_newcomer_and_always_open():
    p = jumpit.parse_list_item({
        "id": 1, "title": "웹 개발자 (신입)", "companyName": "점핏", "techStacks": ["Java", "java", "Spring"],
        "newcomer": True, "minCareer": 0, "maxCareer": 0, "locations": ["서울 구로구"],
        "alwaysOpen": True, "closedAt": "2026-12-01T23:59:59", "jobCategory": "서버/백엔드,웹 풀스택",
    })
    assert (p.career_min, p.career_max) == (0, 0)
    assert p.deadline is None
    assert p.skills == ["Java", "Spring"]
    assert p.categories == ["서버/백엔드", "웹 풀스택"]


def test_jumpit_detail_hidden_is_closed():
    assert jumpit.parse_detail({"invisible": True}).state == "closed"
    d = jumpit.parse_detail({"publishedAt": "2026-11-04 00:00:00", "closedAt": "2026-12-03 23:59:59",
                             "techStacks": [{"stack": "Docker"}], "responsibility": "운영"})
    assert d.fields["posted_at"] == "2026-11-04" and d.fields["deadline"] == "2026-12-03"
    assert d.fields["skills"] == ["Docker"]


def test_remember_list_item():
    p = remember.parse_list_item({
        "id": 9, "title": "MLOps 엔지니어", "status": "published", "min_experience": 6, "max_experience": None,
        "starts_at": "2026-11-03T00:00:00.000+09:00", "ends_at": "2026-12-31T23:59:59.000+09:00",
        "addresses": [{"address_level1": "경기도", "address_level2": "화성시"}],
        "organization": {"name": "(주)이솔", "headhunter": False},
        "job_categories": [{"level1": "AI·데이터", "level2": "MLOps"}],
        "job_description": "모델 서빙", "qualifications": "Kubernetes",
    })
    assert p.company == "(주)이솔" and p.locations == ["경기도 화성시"]
    assert (p.career_min, p.career_max) == (6, None)
    assert (p.posted_at, p.deadline) == ("2026-11-03", "2026-12-31")
    assert p.categories == ["MLOps"] and "Kubernetes" in p.description
    assert remember.parse_detail({"status": "closed"}).state == "closed"


def test_jobplanet_career_codes():
    assert jobplanet.parse_career({"type": [4]}) == (0, None)
    assert jobplanet.parse_career({"type": [1]}) == (0, 0)
    assert jobplanet.parse_career({"type": [2], "years": 4, "maximum_years": 7}) == (4, 7)
    assert jobplanet.parse_career({"type": [2], "years": 5, "maximum_years": 0}) == (5, None)
    assert jobplanet.parse_career({"type": [1, 2], "years": 3}) == (0, None)
    assert jobplanet.parse_career({"type": [2], "years": 0}, "경력무관") == (0, None)


def test_jobplanet_detail_states():
    assert jobplanet.parse_detail({}).state == "missing"
    assert jobplanet.parse_detail({"open": False}).state == "closed"
    d = jobplanet.parse_detail({"open": True, "end_at": "2027.02.01", "skills": ["go"],
                                "location": "서울특별시 송파구 석촌호수로 272"})
    assert d.fields["deadline"] == "2027-02-01"
    assert d.fields["locations"] == ["서울특별시 송파구 석촌호수로 272"]


def test_jobkorea_row():
    p = jobkorea.parse_row({
        "gno": "50299551", "company": "넛지헬스케어㈜", "title": "[킬로] 프론트엔드개발 모집",
        "cells": ["경력3년↑", "학력무관", "서울 강남구", "정규직 외"],
        "keywords": "GUI, 웹표준·웹접근성, GUI", "side": "즉시지원 ~01/02(토)",
        "braze": "[킬로] 프론트엔드개발 모집|50299551|51890363|2026-11-03|2027-01-02|넛지헬스케어㈜|21368538",
    })
    assert p.url == "https://www.jobkorea.co.kr/Recruit/GI_Read/50299551"
    assert (p.career_min, p.career_max, p.career_text) == (3, None, "경력3년↑")
    assert p.locations == ["서울 강남구"] and p.employment_type == "정규직 외"
    assert (p.posted_at, p.deadline) == ("2026-11-03", "2027-01-02")
    assert p.skills == ["GUI", "웹표준·웹접근성"]


def test_jobkorea_row_always_open():
    p = jobkorea.parse_row({"gno": "1", "title": "t", "company": "c", "cells": [], "side": "상시채용",
                            "braze": "t|1|2|2026-11-03|2070-01-01|c|3"})
    assert p.deadline is None


def test_jobkorea_check():
    assert jobkorea.parse_check({"status": 404}).state == "missing"
    assert jobkorea.parse_check({"status": 200, "closedMark": True}).state == "closed"
    assert jobkorea.parse_check({"status": 200, "validThrough": "2020-01-01T23:59"}).state == "closed"
    assert jobkorea.parse_check({"status": 200, "validThrough": "2099-01-01T23:59"}).state == "open"
    assert jobkorea.parse_check({"status": 0}).state == "unknown"


def test_saramin_row():
    p = saramin.parse_row({
        "id": "55331513", "title": "현장 사업관리(PM)", "company": "(주)혁산정보시스템",
        "sectors": ["솔루션", "PM(프로젝트매니저)", "솔루션"], "place": "서울 영등포구 외",
        "career": "3 ~ 15년 · 계약직", "deadline": "~11.22(일)", "posted": "173일 전 등록",
    }, TODAY)
    assert p.url == "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=55331513"
    assert (p.career_min, p.career_max, p.career_text) == (3, 15, "3 ~ 15년")
    assert p.employment_type == "계약직" and p.locations == ["서울 영등포구"]
    assert p.skills == ["솔루션", "PM(프로젝트매니저)"]
    assert (p.deadline, p.posted_at) == ("2026-11-22", "2026-05-14")


def test_saramin_row_variants():
    p = saramin.parse_row({"id": "1", "title": "t", "company": "c", "career": "신입 · 경력 · 정규직 외",
                           "deadline": "D-7", "posted": "2분 전 수정"}, TODAY)
    assert (p.career_min, p.career_max) == (0, None) and p.employment_type == "정규직 외"
    assert p.deadline == "2026-11-10" and p.posted_at is None  # an edit time is not a posting date
    assert saramin.parse_row({"id": "3", "title": "AI &amp; IT 전문가", "company": "c"}, TODAY).title == "AI & IT 전문가"
    p = saramin.parse_row({"id": "2", "title": "t", "company": "c", "career": "경력무관 · 교육생",
                           "deadline": "상시채용", "posted": "3시간 전 등록"}, TODAY)
    assert (p.career_min, p.career_max, p.deadline, p.posted_at) == (0, None, None, "2026-11-03")


def test_saramin_check():
    assert saramin.parse_check({"status": 200, "closed": True, "found": True}, TODAY).state == "closed"
    assert saramin.parse_check({"status": 200, "closed": False, "found": False}, TODAY).state == "missing"
    expired = saramin.parse_check({"status": 200, "found": True, "period": "시작일 2026.10.01 00:00 마감일 2026.11.02 23:59"}, TODAY)
    assert (expired.state, expired.reason) == ("closed", "deadline")
    open_ = saramin.parse_check({"status": 200, "found": True, "period": "시작일 2026.05.14 00:00 마감일 2026.11.13 23:59"}, TODAY)
    assert (open_.state, open_.fields) == ("open", {"deadline": "2026-11-13"})
    assert saramin.parse_check({"status": 200, "found": True, "period": "시작일 2026.10.01 00:00 마감일 채용시"}, TODAY).state == "open"
    assert saramin.parse_check({"status": 0}, TODAY).reason == "http:0"
