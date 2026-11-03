"""리멤버 커리어 — 'SW개발'과 'AI·데이터' 직무.

목록: POST career-api.rememberapp.co.kr/job_postings/search (per 최대 50, 본문까지 포함)
상세: career-api.rememberapp.co.kr/job_postings/{id} (status: published | closed, 없으면 404)
"""
from __future__ import annotations

import json
import random
from collections.abc import Iterator

from ..browser import parse_json
from ..models import Detail, Posting
from ..normalize import to_date, unique
from .base import Scraper, sections

API = "https://career-api.rememberapp.co.kr"
PAGE_SIZE = 50
JOB_CATEGORIES = [{"level1": "SW개발"}, {"level1": "AI·데이터"}]


def _locations(item: dict) -> list[str]:
    out = [
        " ".join(x for x in (a.get("address_level1"), a.get("address_level2")) if x)
        for a in item.get("addresses") or []
    ]
    if not out and (n := item.get("normalized_address")):
        out = [" ".join(x for x in (n.get("level1"), n.get("level2")) if x)]
    return [x for x in out if x]


def _fields(item: dict) -> dict:
    lo, hi = item.get("min_experience"), item.get("max_experience")
    return {
        "title": (item.get("title") or "").strip(),
        "locations": _locations(item),
        "career_min": 0 if lo is None and hi is not None else lo,
        "career_max": hi,
        "categories": unique(c.get("level2") for c in item.get("job_categories") or []),
        "deadline": to_date(item.get("ends_at")),
        "posted_at": to_date(item.get("starts_at")),
        "description": sections(
            ("소개", item.get("introduction")),
            ("주요업무", item.get("job_description")),
            ("자격요건", item.get("qualifications")),
            ("우대사항", item.get("preferred_qualifications")),
            ("채용절차", item.get("recruiting_process")),
            ("기타", item.get("additional_information")),
        ),
    }


def parse_list_item(item: dict) -> Posting:
    org = item.get("organization") or {}
    return Posting(
        source="remember",
        source_id=str(item["id"]),
        url=f"https://career.rememberapp.co.kr/job/posting/{item['id']}",
        company=(org.get("name") or "").strip(),
        is_open=item.get("status") == "published",
        extra={"thumbnail": org.get("logo"), "headhunter": bool(org.get("headhunter"))},
        **_fields(item),
    )


def parse_detail(data: dict) -> Detail:
    if data.get("status") == "published":
        return Detail("open", _fields(data))
    return Detail("closed", reason=f"status:{data.get('status')}")


class RememberScraper(Scraper):
    source = "remember"
    label = "리멤버"
    home_url = "https://career.rememberapp.co.kr/job/postings"
    enrich_with_details = False  # the search API already returns full descriptions
    # The API blocks a client after ~27 requests in 30 seconds and lifts it a minute or so later.
    min_interval = 2.6
    max_verify = 150

    def iter_listing(self) -> Iterator[list[Posting]]:
        seed = random.randint(1, 99_999_999)  # keep result order stable across pages
        page, seen = 1, 0
        while True:
            body = {
                "sort": "starts_at_desc",
                "search": {"include_applied_job_posting": False, "job_category_names": JOB_CATEGORIES},
                "page": page,
                "per": PAGE_SIZE,
                "seed": seed,
            }
            data = self.get_json(
                f"{API}/job_postings/search",
                method="POST",
                body=json.dumps(body, ensure_ascii=False),
                headers={"Content-Type": "application/json"},
            )
            meta = data.get("meta") or {}
            self.reported_total = meta.get("total_count")
            items = data.get("data") if isinstance(data.get("data"), list) else []
            if items:
                seen += len(items)
                yield [parse_list_item(item) for item in items]
            total_pages = meta.get("total_pages") or 0
            if not items or page >= total_pages:
                break
            page += 1
            self.pause()
        self.check_total(seen)

    def fetch_details(self, source_ids: list[str]) -> dict[str, Detail]:
        out: dict[str, Detail] = {}
        for i, sid in enumerate(source_ids):  # one at a time, to stay under the rate limit
            if i:
                self.pause()
            res = self.tab.fetch(f"{API}/job_postings/{sid}")
            data = (parse_json(res.get("text")) or {}).get("data")
            if res["status"] == 404:
                out[sid] = Detail("missing", reason="not_found")
            elif res["status"] == 200 and data:
                out[sid] = parse_detail(data)
            else:
                out[sid] = Detail("unknown", reason=f"http:{res['status']}")
        return out
