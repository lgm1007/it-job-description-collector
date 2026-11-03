"""원티드 — 개발 직군(tag 518) 전체.

목록: /api/v4/jobs (100건씩 offset 페이징, status·due_time 포함)
상세: /_next/data/{buildId}/wd/{id}.json (등록일 confirm_time·본문, 약 3KB)
      실패하면 /api/v4/jobs/{id} (삭제된 공고는 404)
"""
from __future__ import annotations

from collections.abc import Iterator

from ..browser import parse_json
from ..models import Detail, Posting
from ..normalize import to_date
from .base import Scraper, sections

PAGE_SIZE = 100
LIST_URL = (
    "/api/v4/jobs?country=kr&tag_type_ids=518&job_sort=job.latest_order"
    "&locations=all&years=-1&limit={limit}&offset={offset}"
)
EMPLOYMENT = {"regular": "정규직", "contract": "계약직", "intern": "인턴", "freelance": "프리랜서"}


def _career(annual_from, annual_to) -> tuple[int | None, int | None]:
    if annual_to is not None and annual_to >= 100:  # 100 = 상한 없음
        annual_to = None
    return annual_from, annual_to


def parse_list_item(item: dict) -> Posting:
    addr = item.get("address") or {}
    location = " ".join(x for x in (addr.get("location"), addr.get("district")) if x)
    career_min, career_max = _career(item.get("annual_from"), item.get("annual_to"))
    return Posting(
        source="wanted",
        source_id=str(item["id"]),
        url=f"https://www.wanted.co.kr/wd/{item['id']}",
        title=(item.get("position") or "").strip(),
        company=((item.get("company") or {}).get("name") or "").strip(),
        locations=[location] if location else [],  # full_location often omits the 시/도
        career_min=career_min,
        career_max=career_max,
        deadline=to_date(item.get("due_time")),
        is_open=item.get("status") == "active" and not item.get("hidden"),
        extra={"thumbnail": (item.get("title_img") or {}).get("thumb"), "address": addr.get("full_location")},
    )


def _state(job: dict) -> tuple[str, str | None]:
    if job.get("status") == "active" and not job.get("hidden"):
        return "open", None
    return "closed", f"status:{job.get('status')}"


def parse_detail(data: dict) -> Detail:
    """`data` is pageProps.initialData from the Next.js data route."""
    state, reason = _state(data)
    child_tags = ((data.get("category_tag") or {}).get("child_tags")) or []
    fields = {
        "deadline": to_date(data.get("due_time")),
        "posted_at": to_date(data.get("confirm_time")),
        "employment_type": EMPLOYMENT.get(data.get("employment_type") or ""),
        "categories": [t.get("text") for t in child_tags if t.get("text")],
        "description": sections(
            ("소개", data.get("intro")),
            ("주요업무", data.get("main_tasks")),
            ("자격요건", data.get("requirements")),
            ("우대사항", data.get("preferred_points")),
            ("혜택 및 복지", data.get("benefits")),
            ("채용 전형", data.get("hire_rounds")),
        ),
    }
    return Detail(state, fields, reason)


def parse_api_detail(job: dict) -> Detail:
    """Fallback shape from /api/v4/jobs/{id} (no posting date)."""
    state, reason = _state(job)
    detail = job.get("detail") or {}
    fields = {
        "deadline": to_date(job.get("due_time")),
        "skills": [t.get("title") or t.get("text") for t in job.get("skill_tags") or [] if isinstance(t, dict)],
        "description": sections(
            ("소개", detail.get("intro")),
            ("주요업무", detail.get("main_tasks")),
            ("자격요건", detail.get("requirements")),
            ("우대사항", detail.get("preferred_points")),
            ("혜택 및 복지", detail.get("benefits")),
        ),
    }
    return Detail(state, fields, reason)


class WantedScraper(Scraper):
    source = "wanted"
    label = "원티드"
    home_url = "https://www.wanted.co.kr/wdlist/518?country=kr&job_sort=job.latest_order&years=-1&locations=all"

    _build_id: str | None = None
    _build_id_refreshed = False

    def iter_listing(self) -> Iterator[list[Posting]]:
        offset = 0
        while True:
            data = self.get_json(LIST_URL.format(limit=PAGE_SIZE, offset=offset))
            items = data.get("data") or []
            if items:
                yield [parse_list_item(item) for item in items]
            if not items or not (data.get("links") or {}).get("next"):
                break
            offset += PAGE_SIZE
            self.pause()
        self.listing_complete = True  # the API reports no total; reaching `next: null` is the signal

    def _current_build_id(self) -> str | None:
        if self._build_id is None:
            self._build_id = self.tab.evaluate(
                "(() => { const el = document.getElementById('__NEXT_DATA__');"
                " return el ? JSON.parse(el.textContent).buildId : null; })()"
            )
        return self._build_id

    def fetch_details(self, source_ids: list[str]) -> dict[str, Detail]:
        out: dict[str, Detail] = {}
        fallback: list[str] = []
        build_id = self._current_build_id()
        if build_id:
            responses = self.get_many([{"url": f"/_next/data/{build_id}/wd/{sid}.json"} for sid in source_ids])
            for sid, res in zip(source_ids, responses):
                payload = parse_json(res.get("text")) if res["status"] == 200 else None
                if initial := ((payload or {}).get("pageProps") or {}).get("initialData"):
                    out[sid] = parse_detail(initial)
                else:
                    fallback.append(sid)
            if source_ids and len(fallback) == len(source_ids) and not self._build_id_refreshed:
                # A deploy changes the buildId; reload once to pick up the new one.
                self._build_id_refreshed = True
                self._build_id = None
                self.tab.goto(self.home_url)
                self.prepare()
        else:
            fallback = list(source_ids)
        if fallback:
            responses = self.get_many([{"url": f"/api/v4/jobs/{sid}"} for sid in fallback])
            for sid, res in zip(fallback, responses):
                job = (parse_json(res.get("text")) or {}).get("job") if res["status"] == 200 else None
                if res["status"] == 404:
                    out[sid] = Detail("missing", reason="not_found")
                elif job:
                    out[sid] = parse_api_detail(job)
                else:
                    out[sid] = Detail("unknown", reason=f"http:{res['status']}")
        return out
