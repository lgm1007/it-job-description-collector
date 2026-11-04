from datetime import date

import pytest

from jdc.normalize import (
    career_from_text,
    career_label,
    dedupe_key,
    month_day_to_date,
    normalize_location,
    split_terms,
    term_pattern,
    to_date,
)


@pytest.mark.parametrize("raw, expected", [
    ("서울특별시 송파구 석촌호수로 272", ("서울", "서울 송파구")),
    ("경기 성남시 분당구", ("경기", "경기 성남시")),
    ("서울 강남구", ("서울", "서울 강남구")),
    ("서울특별시 전체", ("서울", None)),
    ("세종특별자치시", ("세종", None)),
    ("강원특별자치도 춘천시", ("강원", "강원 춘천시")),
    ("주소: 서울특별시 서초구 서초대로77길 17 13층", ("서울", "서울 서초구")),
    ("The Founders East (본사 동관): 서울특별시 강남구 영동대로 502", ("서울", "서울 강남구")),
    ("서울특별 마포구 양화로 188, 8층", ("서울", "서울 마포구")),
    ("강남구 테헤란로 521", ("서울", "서울 강남구")),
    ("성남시 분당구 판교역로 166", ("경기", "경기 성남시")),
    ("판교 테크노밸리", ("경기", "경기 성남시")),
    ("중구 퇴계로 385", ("기타", None)),  # 중구 exists in several cities
    ("전남광주 여수시 외", ("전남", "전남 여수시")),
    ("인천전체", ("인천", None)),
    ("아시아·중동 말레이시아", ("해외", None)),
    ("전남광주통합특별시 광산구 첨단과기로", ("광주", "광주 광산구")),
    ("재택근무", ("원격", None)),
    ("미국 캘리포니아", ("해외", None)),
    ("여의공원로 115", ("기타", None)),
    ("", (None, None)),
])
def test_normalize_location(raw, expected):
    assert normalize_location(raw) == expected


@pytest.mark.parametrize("text, expected", [
    ("경력무관", (0, None)),
    ("신입", (0, 0)),
    ("인턴", (0, 0)),
    ("신입·경력", (0, None)),
    ("신입·경력1년↑", (0, None)),
    ("경력3년↑", (3, None)),
    ("경력1~3년", (1, 3)),
    ("경력 5년 이상", (5, None)),
    ("경력", (1, None)),
    ("경력(년수무관)", (1, None)),
    ("신입 · 경력(연차무관)", (0, None)),
    (None, (None, None)),
])
def test_career_from_text(text, expected):
    assert career_from_text(text) == expected


@pytest.mark.parametrize("bounds, expected", [
    ((0, 0), "신입"),
    ((0, None), "경력무관"),
    ((3, None), "3년 이상"),
    ((1, 3), "1~3년"),
    ((0, 4), "신입~4년"),
    ((5, 5), "5년"),
])
def test_career_label(bounds, expected):
    assert career_label(*bounds) == expected


def test_career_label_falls_back_to_site_wording():
    assert career_label(None, None, "경력(연차무관)") == "경력(연차무관)"


@pytest.mark.parametrize("value, expected", [
    ("2026-11-15", "2026-11-15"),
    ("2026-12-03T23:59:59", "2026-12-03"),
    ("2026-12-03 23:59:59", "2026-12-03"),
    ("2024-11-19T23:59:59.000+09:00", "2024-11-19"),
    ("2026-11-03T20:00:00Z", "2026-11-04"),  # UTC evening is the next day in Korea
    ("2027.02.01", "2027-02-01"),
    ("2070-01-01", None),  # 상시채용 placeholder
    (None, None),
    ("", None),
])
def test_to_date(value, expected):
    assert to_date(value) == expected


def test_month_day_to_date_rolls_into_next_year():
    today = date(2026, 11, 3)
    assert month_day_to_date(1, 2, today) == "2027-01-02"
    assert month_day_to_date(12, 3, today) == "2026-12-03"
    assert month_day_to_date(11, 1, today) == "2026-11-01"  # just passed: stays in the past


@pytest.mark.parametrize("text, expected", [
    ("~01/02(토)", "2027-01-02"),
    ("즉시지원 1시간 전 등록 ~11.13(금)", "2026-11-13"),
    ("D-7", "2026-11-10"),
    ("오늘마감", "2026-11-03"),
    ("내일 마감", "2026-11-04"),
    ("상시채용", None),
    ("채용시", None),
    (None, None),
])
def test_deadline_from_text(text, expected):
    from jdc.normalize import deadline_from_text

    assert deadline_from_text(text, date(2026, 11, 3)) == expected


def test_dedupe_key_ignores_company_suffixes_and_punctuation():
    assert dedupe_key("(주)버즈빌", "[광고] 백엔드 엔지니어") == dedupe_key("버즈빌", "[광고]백엔드 엔지니어")
    assert dedupe_key("Foo Inc.", "Backend") == dedupe_key("foo", "backend")
    assert dedupe_key("버즈빌", "백엔드") != dedupe_key("버즈빌", "프론트엔드")


def test_split_terms():
    assert split_terms("  Kotlin, Spring  백엔드 ") == ["kotlin", "spring", "백엔드"]
    assert split_terms(None) == []


def test_term_pattern_short_and_ambiguous_terms():
    go = term_pattern("go")
    assert go.search("go 백엔드") and go.search("go/kotlin") and not go.search("google")
    assert term_pattern("ai").search("생성형ai 엔지니어") and not term_pattern("ai").search("email")
    java = term_pattern("java")
    assert java.search("java, spring") and not java.search("javascript")
    cpp = term_pattern("c")
    assert not cpp.search("c++ 개발") and cpp.search("c 언어")
    assert term_pattern("kotlin") is None and term_pattern("백엔드") is None
