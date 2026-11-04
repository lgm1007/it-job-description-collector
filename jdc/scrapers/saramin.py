"""사람인 — 직무 'IT개발·데이터'(cat_mcls 2).

목록: /zf_user/jobs/list/job-category?...&isAjaxRequest=1 이 {total_count, contents(HTML)}를 돌려주므로
      페이지 안에서 DOMParser로 읽어 필요한 값만 JSON으로 넘깁니다 (page_count=100, 최신 등록순).
확인: POST /zf_user/jobs/relay/view-ajax — '마감되었습니다'·'접수마감'이면 마감, 마감일이 지났어도 마감.
      본문은 대부분 이미지라 목록의 직무 키워드로 검색합니다.
"""
from __future__ import annotations

import html
import re
from collections.abc import Iterator
from datetime import date, timedelta

from ..models import Detail, Posting
from ..normalize import EMPLOYMENT, career_from_text, deadline_from_text, now_kst, unique
from .base import ScrapeError, Scraper

PAGE_SIZE = 100
LIST_QUERY = (
    "cat_mcls=2&panel_type=&search_optional_item=n&search_done=y&panel_count=y&preview=y"
    f"&sort=RD&page_count={PAGE_SIZE}&isAjaxRequest=1&page="
)

_LIST_JS = r"""
async (query) => {
  const res = await fetch('/zf_user/jobs/list/job-category?' + query, {headers: {'X-Requested-With': 'XMLHttpRequest'}});
  if (!res.ok) return {status: res.status, total: null, rows: []};
  let data;
  try { data = await res.json(); } catch (e) { return {status: -1, total: null, rows: []}; }
  const doc = new DOMParser().parseFromString(data.contents || '', 'text/html');
  const text = (el) => (el ? el.textContent : '').replace(/\s+/g, ' ').trim();
  const rows = [...doc.querySelectorAll('div.list_item[id^="rec-"]')].map((el) => {
    const link = el.querySelector('.job_tit a');
    return {
      id: el.id.slice(4),
      title: link ? (link.getAttribute('title') || text(link)) : '',
      company: text(el.querySelector('.company_nm .str_tit')) || text(el.querySelector('.company_nm')),
      sectors: [...el.querySelectorAll('.job_sector span')].map(text).filter(Boolean),
      place: text(el.querySelector('.work_place')),
      career: text(el.querySelector('.career')),
      deadline: text(el.querySelector('.support_detail .date')),
      posted: text(el.querySelector('.support_detail .deadlines')),
    };
  });
  const total = Number(String(data.total_count || '').replace(/[^0-9]/g, ''));
  return {status: res.status, total: total || null, rows};
}
"""

_CHECK_JS = r"""
async (ids, concurrency) => {
  const one = async (id) => {
    try {
      const body = new URLSearchParams({rec_idx: id, view_type: 'list'});
      const res = await fetch('/zf_user/jobs/relay/view-ajax', {
        method: 'POST', body: body.toString(),
        headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest'},
      });
      if (res.status !== 200) return {id, status: res.status};
      const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
      const text = (doc.body ? doc.body.textContent : '').replace(/\s+/g, ' ');
      const period = doc.querySelector('.info_period');
      return {
        id, status: 200,
        closed: /채용정보는 마감되었습니다/.test(text)
          || [...doc.querySelectorAll('button, a')].some((b) => b.textContent.trim() === '접수마감'),
        found: !!(period || doc.querySelector('.tit_job, .jv_header')),
        period: period ? period.textContent.replace(/\s+/g, ' ').trim() : '',
      };
    } catch (e) {
      return {id, status: 0, error: String(e)};
    }
  };
  const out = [];
  let next = 0;
  const worker = async () => { while (next < ids.length) { const id = ids[next++]; out.push(await one(id)); } };
  await Promise.all(Array.from({length: Math.min(concurrency, ids.length)}, worker));
  return out;
}
"""


def posted_from_text(text: str | None, today: date | None = None) -> str | None:
    """'173일 전 등록', '3시간 전 등록' -> date. '… 수정' is an edit time, not a posting date."""
    t = (text or "").replace(" ", "")
    if "등록" not in t:
        return None
    today = today or now_kst().date()
    if m := re.search(r"(\d+)일전", t):
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    if re.search(r"\d+(분|시간)전|방금", t):
        return today.isoformat()
    if m := re.search(r"(\d{1,2})/(\d{1,2})", t):
        posted = date(today.year, int(m.group(1)), int(m.group(2)))
        return (posted if posted <= today else posted.replace(year=today.year - 1)).isoformat()
    return None


def parse_row(row: dict, today: date | None = None) -> Posting:
    # '경력 4년↑ · 정규직', '신입 · 경력 · 정규직 외', '3 ~ 15년 · 계약직'
    parts = [p.strip() for p in (row.get("career") or "").split("·") if p.strip()]
    employment = [p for p in parts if EMPLOYMENT.search(p)]
    career_text = " · ".join(p for p in parts if p not in employment) or None
    career_min, career_max = career_from_text(career_text)
    place = re.sub(r"\s*외$", "", row.get("place") or "").strip()
    rec_idx = str(row["id"])
    return Posting(
        source="saramin",
        source_id=rec_idx,
        url=f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={rec_idx}",
        title=html.unescape(row.get("title") or "").strip(),  # titles arrive double-escaped ('&amp;')
        company=html.unescape(row.get("company") or "").strip(),
        locations=[place] if place else [],
        career_min=career_min,
        career_max=career_max,
        career_text=career_text,
        skills=unique(row.get("sectors") or []),
        employment_type=" · ".join(employment) or None,
        deadline=deadline_from_text(row.get("deadline"), today),
        posted_at=posted_from_text(row.get("posted"), today),
    )


def parse_check(result: dict, today: date | None = None) -> Detail:
    status = result.get("status")
    if status == 404:
        return Detail("missing", reason="not_found")
    if status != 200:
        return Detail("unknown", reason=f"http:{status}")
    if result.get("closed"):
        return Detail("closed", reason="closed_mark")
    if not result.get("found"):
        return Detail("missing", reason="not_found")
    today = today or now_kst().date()
    if m := re.search(r"마감일\s*(\d{4})\.(\d{2})\.(\d{2})", result.get("period") or ""):
        deadline = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if deadline < today:
            return Detail("closed", reason="deadline")
        return Detail("open", {"deadline": deadline.isoformat()})
    return Detail("open")


class SaraminScraper(Scraper):
    source = "saramin"
    label = "사람인"
    home_url = "https://www.saramin.co.kr/zf_user/jobs/list/job-category?cat_mcls=2"
    enrich_with_details = False  # 본문은 대부분 이미지라 목록의 직무 키워드로 검색합니다

    def iter_listing(self) -> Iterator[list[Posting]]:
        page, seen = 1, 0
        today = now_kst().date()
        while True:
            data = None
            for _ in range(3):
                data = self.tab.call(_LIST_JS, f"{LIST_QUERY}{page}", timeout=90)
                if data and data.get("status") == 200:
                    break
                self.pause()
            if not data or data.get("status") != 200:
                raise ScrapeError(f"사람인 목록 {page}페이지 요청 실패 (HTTP {data and data.get('status')})")
            if data.get("total") is not None:
                self.reported_total = data["total"]
            rows = [r for r in data.get("rows") or [] if r.get("id")]
            if rows:
                seen += len(rows)
                yield [parse_row(r, today) for r in rows]
            if len(rows) < PAGE_SIZE or (self.reported_total is not None and page * PAGE_SIZE >= self.reported_total):
                break
            page += 1
            self.pause()
        self.check_total(seen)

    def fetch_details(self, source_ids: list[str]) -> dict[str, Detail]:
        results = self.tab.call(
            _CHECK_JS, source_ids, self.settings.detail_concurrency, timeout=30 * len(source_ids) + 30
        )
        out = {str(r["id"]): parse_check(r) for r in results or []}
        for sid in source_ids:
            out.setdefault(sid, Detail("unknown", reason="no_result"))
        return out
