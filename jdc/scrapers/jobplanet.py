"""잡플래닛 — 직군 '개발'(11600)과 '데이터'(11912).

목록: /api/v3/job/postings (page_size=100, total_count 제공)
상세: /api/v1/job/postings/{id} (open 여부·본문, 없는 공고는 data: {})
"""
from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urlencode

from ..browser import parse_json
from ..models import Detail, Posting
from ..normalize import to_date, unique
from .base import Scraper, sections

PAGE_SIZE = 100
OCCUPATIONS = "11600,11912"
# annual.type codes as the site uses them
NEWCOMER, EXPERIENCED, ANY = 1, 2, 4


def parse_career(annual: dict, career_text: str | None = None) -> tuple[int | None, int | None]:
    if career_text and "무관" in career_text:  # type is sometimes [2] while the site shows 경력무관
        return 0, None
    types = set(annual.get("type") or annual.get("types") or [])
    years = annual.get("years", annual.get("year")) or 0
    max_years = annual.get("maximum_years", annual.get("maximum_year")) or 0
    if ANY in types:
        return 0, None
    if EXPERIENCED in types:
        lo = 0 if NEWCOMER in types else (years or 1)
        return lo, max_years or None
    if NEWCOMER in types:
        return 0, 0
    return None, None


def parse_list_item(item: dict) -> Posting:
    company = item.get("company") or {}
    career_min, career_max = parse_career(item.get("annual") or {}, item.get("career_text"))
    occupations = item.get("occupation_names") or {}
    return Posting(
        source="jobplanet",
        source_id=str(item["id"]),
        url=f"https://www.jobplanet.co.kr/job/search?posting_ids%5B%5D={item['id']}",
        title=(item.get("title") or "").strip(),
        company=(company.get("name") or "").strip(),
        locations=item.get("cities") or ([company["city_name"]] if company.get("city_name") else []),
        career_min=career_min,
        career_max=career_max,
        career_text=item.get("career_text"),
        skills=unique(item.get("skills") or []),
        categories=unique(occupations.get("level2") or []),
        employment_type=item.get("job_type"),
        deadline=to_date(item.get("end_at")),
        posted_at=to_date(item.get("start_at")),
        extra={
            "thumbnail": item.get("logo_thumb_url"),
            "jobkorea_posting_id": item.get("jobkorea_posting_id"),
        },
    )


def parse_detail(data: dict) -> Detail:
    if not data:
        return Detail("missing", reason="not_found")
    if not data.get("open"):
        return Detail("closed", reason="not_open")
    fields = {
        "deadline": to_date(data.get("end_at")),
        "skills": unique(data.get("skills") or []),
        "description": sections(
            ("소개", data.get("introduction")),
            ("주요업무", data.get("primary_responsibility")),
            ("자격요건", data.get("required_qualification")),
            ("우대사항", data.get("preferred_skill")),
            ("복지", data.get("benefit")),
            ("채용절차", data.get("hiring_process")),
            ("기타", data.get("etc")),
        ),
    }
    if data.get("location"):
        fields["locations"] = [data["location"]]
    return Detail("open", fields)


class JobPlanetScraper(Scraper):
    source = "jobplanet"
    label = "잡플래닛"
    home_url = "https://www.jobplanet.co.kr/job"

    def iter_listing(self) -> Iterator[list[Posting]]:
        page, seen = 1, 0
        while True:
            query = urlencode({
                "occupation_level1": OCCUPATIONS, "occupation_level2": "", "years_of_experience": "",
                "review_score": "", "job_type": "", "city": "", "education_level_id": "",
                "order_by": "recent", "page": page, "page_size": PAGE_SIZE,
            })
            data = (self.get_json(f"/api/v3/job/postings?{query}").get("data")) or {}
            self.reported_total = data.get("total_count")
            items = data.get("recruits") or []
            if items:
                seen += len(items)
                yield [parse_list_item(item) for item in items]
            if len(items) < PAGE_SIZE or (self.reported_total is not None and page * PAGE_SIZE >= self.reported_total):
                break
            page += 1
            self.pause()
        self.check_total(seen)

    def fetch_details(self, source_ids: list[str]) -> dict[str, Detail]:
        out: dict[str, Detail] = {}
        responses = self.get_many([{"url": f"/api/v1/job/postings/{sid}"} for sid in source_ids])
        for sid, res in zip(source_ids, responses):
            payload = parse_json(res.get("text"))
            if res["status"] == 200 and isinstance(payload, dict) and "data" in payload:
                out[sid] = parse_detail(payload["data"] or {})
            elif res["status"] == 404:
                out[sid] = Detail("missing", reason="not_found")
            else:
                out[sid] = Detail("unknown", reason=f"http:{res['status']}")
        return out
