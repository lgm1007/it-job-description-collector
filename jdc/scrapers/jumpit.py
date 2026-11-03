"""점핏 (사람인 개발자 플랫폼) — 전 포지션이 개발 직군.

목록: jumpit-api.saramin.co.kr/api/positions (size=100, totalCount 제공)
상세: jumpit-api.saramin.co.kr/api/position/{id} (등록일·본문, 없는 공고는 400 C003)
"""
from __future__ import annotations

from collections.abc import Iterator

from ..browser import parse_json
from ..models import Detail, Posting
from ..normalize import to_date, unique
from .base import Scraper, sections

API = "https://jumpit-api.saramin.co.kr/api"
PAGE_SIZE = 100


def _career(newcomer, min_career, max_career) -> tuple[int | None, int | None]:
    lo = 0 if newcomer else min_career
    hi = max_career if max_career else None
    if newcomer and not min_career and max_career == 0:
        hi = 0  # 신입만
    return lo, hi


def parse_list_item(item: dict) -> Posting:
    career_min, career_max = _career(item.get("newcomer"), item.get("minCareer"), item.get("maxCareer"))
    return Posting(
        source="jumpit",
        source_id=str(item["id"]),
        url=f"https://jumpit.saramin.co.kr/position/{item['id']}",
        title=(item.get("title") or "").strip(),
        company=(item.get("companyName") or "").strip(),
        locations=[x for x in item.get("locations") or [] if x],
        career_min=career_min,
        career_max=career_max,
        skills=unique(item.get("techStacks") or []),
        categories=unique((item.get("jobCategory") or "").split(",")),
        deadline=None if item.get("alwaysOpen") else to_date(item.get("closedAt")),
        extra={"thumbnail": item.get("logo")},
    )


def parse_detail(result: dict) -> Detail:
    hidden = result.get("invisible") or result.get("hiddenPosition")
    fields = {
        "posted_at": to_date(result.get("publishedAt")),
        "deadline": None if result.get("alwaysOpen") else to_date(result.get("closedAt")),
        "skills": unique(t.get("stack") for t in result.get("techStacks") or [] if isinstance(t, dict)),
        "description": sections(
            ("주요업무", result.get("responsibility")),
            ("자격요건", result.get("qualifications")),
            ("우대사항", result.get("preferredRequirements")),
            ("복지 및 혜택", result.get("welfares")),
            ("채용절차", result.get("recruitProcess")),
            ("서비스 소개", result.get("serviceInfo")),
        ),
    }
    if result.get("location"):
        fields["locations"] = [result["location"]]
    return Detail("closed" if hidden else "open", fields, "hidden" if hidden else None)


class JumpitScraper(Scraper):
    source = "jumpit"
    label = "점핏"
    home_url = "https://jumpit.saramin.co.kr/positions?sort=reg_dt"

    def iter_listing(self) -> Iterator[list[Posting]]:
        page, seen = 1, 0
        while True:
            data = self.get_json(f"{API}/positions?sort=reg_dt&highlight=false&page={page}&size={PAGE_SIZE}")
            result = data.get("result") or {}
            self.reported_total = result.get("totalCount")
            items = result.get("positions") or []
            if items:
                seen += len(items)
                yield [parse_list_item(item) for item in items]
            if len(items) < PAGE_SIZE or (self.reported_total is not None and seen >= self.reported_total):
                break
            page += 1
            self.pause()
        self.check_total(seen)

    def fetch_details(self, source_ids: list[str]) -> dict[str, Detail]:
        out: dict[str, Detail] = {}
        responses = self.get_many([{"url": f"{API}/position/{sid}"} for sid in source_ids])
        for sid, res in zip(source_ids, responses):
            payload = parse_json(res.get("text")) or {}
            if res["status"] == 200 and payload.get("result"):
                out[sid] = parse_detail(payload["result"])
            elif res["status"] in (400, 404) and payload.get("code") in ("C003", None):
                out[sid] = Detail("missing", reason="not_found")
            else:
                out[sid] = Detail("unknown", reason=f"http:{res['status']}")
        return out
