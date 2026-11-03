"""잡코리아 — 직무 'AI·개발·데이터'(dutyCtgr 10031).

목록: POST /Recruit/Home/_GI_List/ 가 HTML 조각을 돌려주므로 페이지 안에서 DOMParser로 읽어
      필요한 값만 JSON으로 넘깁니다 (pagesize=100, 총 건수는 #hdnGICnt).
확인: /Recruit/GI_Read/{gno} — 삭제된 공고는 404, 그 외에는 JSON-LD의 validThrough로 판단합니다.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import timedelta

from ..models import Detail, Posting
from ..normalize import career_from_text, month_day_to_date, normalize_location, now_kst, to_date, unique
from .base import ScrapeError, Scraper

PAGE_SIZE = 100

_LIST_JS = r"""
async (page, pageSize) => {
  const body = new URLSearchParams({
    isDefault: 'false', 'condition[menucode]': 'duty', 'condition[dutyCtgr]': '10031',
    page: String(page), direct: '0', order: '2', pagesize: String(pageSize),
    tabindex: '0', onePick: '0', confirm: '0', profile: '0',
  });
  const res = await fetch('/Recruit/Home/_GI_List/', {
    method: 'POST', body: body.toString(),
    headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest'},
  });
  if (!res.ok) return {status: res.status, total: null, rows: []};
  const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
  const text = (el) => (el ? el.textContent : '').replace(/\s+/g, ' ').trim();
  const total = ((doc.querySelector('#hdnGICnt') || {}).value || '').replace(/[^0-9]/g, '');
  const rows = [...doc.querySelectorAll('tr.devloopArea')].map((tr) => {
    const link = tr.querySelector('td.tplTit strong a');
    return {
      gno: tr.dataset.gno,
      company: text(tr.querySelector('td.tplCo a.link')),
      title: link ? (link.getAttribute('title') || text(link)) : '',
      cells: [...tr.querySelectorAll('td.tplTit p.etc span.cell')].map(text).filter(Boolean),
      keywords: text(tr.querySelector('td.tplTit p.dsc')),
      braze: (tr.querySelector('[data-brazeinfo]') || {dataset: {}}).dataset.brazeinfo || '',
      side: text(tr.querySelector('td.odd')),
    };
  });
  return {status: res.status, total: total ? Number(total) : null, rows};
}
"""

_CHECK_JS = r"""
async (gnos, concurrency) => {
  const one = async (gno) => {
    try {
      const res = await fetch('/Recruit/GI_Read/' + gno);
      if (res.status !== 200) return {gno, status: res.status};
      const html = await res.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      let posting = null;
      for (const s of doc.querySelectorAll('script[type="application/ld+json"]')) {
        try { const d = JSON.parse(s.textContent); if (d['@type'] === 'JobPosting') posting = d; } catch (e) {}
      }
      return {
        gno, status: 200,
        validThrough: posting && posting.validThrough, datePosted: posting && posting.datePosted,
        closedMark: /(접수가 마감|마감된 공고|채용이 마감|모집이 마감)/.test(html),
      };
    } catch (e) {
      return {gno, status: 0, error: String(e)};
    }
  };
  const out = [];
  let next = 0;
  const worker = async () => { while (next < gnos.length) { const g = gnos[next++]; out.push(await one(g)); } };
  await Promise.all(Array.from({length: Math.min(concurrency, gnos.length)}, worker));
  return out;
}
"""

_EMPLOYMENT = re.compile(r"정규직|계약직|인턴|프리랜서|파견직|병역특례|위촉직|아르바이트|교육생|전환형")


def _deadline_from_side(side: str) -> str | None:
    today = now_kst().date()
    if "오늘마감" in side.replace(" ", ""):
        return today.isoformat()
    if "내일마감" in side.replace(" ", ""):
        return (today + timedelta(days=1)).isoformat()
    if m := re.search(r"~\s*(\d{1,2})/(\d{1,2})", side):
        return month_day_to_date(int(m.group(1)), int(m.group(2)), today)
    return None  # 상시채용 / 채용시


def parse_row(row: dict) -> Posting:
    cells = row.get("cells") or []
    career_text = next((c for c in cells if re.match(r"(신입|경력|인턴)", c)), None)
    location = next((c for c in cells if normalize_location(c)[0] not in (None, "기타")), None)
    employment = next((c for c in cells if _EMPLOYMENT.search(c)), None)
    # data-brazeinfo: 제목|gno|?|시작일|마감일|회사|회사번호 (상시채용은 2070년대 날짜)
    braze = (row.get("braze") or "").split("|")
    posted_at = to_date(braze[3]) if len(braze) > 4 else None
    if len(braze) > 4 and re.match(r"\d{4}-\d{2}-\d{2}", braze[4]):
        deadline = to_date(braze[4])
    else:
        deadline = _deadline_from_side(row.get("side") or "")
    career_min, career_max = career_from_text(career_text)
    gno = str(row["gno"])
    return Posting(
        source="jobkorea",
        source_id=gno,
        url=f"https://www.jobkorea.co.kr/Recruit/GI_Read/{gno}",
        title=(row.get("title") or "").strip(),
        company=(row.get("company") or "").strip(),
        locations=[location] if location else [],
        career_min=career_min,
        career_max=career_max,
        career_text=career_text,
        skills=unique((row.get("keywords") or "").split(",")),
        employment_type=employment,
        deadline=deadline,
        posted_at=posted_at,
    )


def parse_check(result: dict) -> Detail:
    status = result.get("status")
    if status == 404:
        return Detail("missing", reason="not_found")
    if status != 200:
        return Detail("unknown", reason=f"http:{status}")
    if result.get("closedMark"):
        return Detail("closed", reason="closed_mark")
    # 상시채용 공고도 validThrough가 1년 뒤로 채워져 있어 마감일로 저장하지 않고, 지났는지만 봅니다.
    valid_through = to_date(result.get("validThrough"))
    if valid_through and valid_through < now_kst().date().isoformat():
        return Detail("closed", reason="deadline")
    return Detail("open")


class JobKoreaScraper(Scraper):
    source = "jobkorea"
    label = "잡코리아"
    home_url = "https://www.jobkorea.co.kr/recruit/joblist?menucode=duty"
    enrich_with_details = False  # 상세 본문은 대부분 이미지라 목록의 키워드로 검색합니다

    def iter_listing(self) -> Iterator[list[Posting]]:
        page, seen = 1, 0
        while True:
            data = None
            for attempt in range(3):
                data = self.tab.call(_LIST_JS, page, PAGE_SIZE, timeout=90)
                if data and data.get("status") == 200:
                    break
                self.pause()
            if not data or data.get("status") != 200:
                raise ScrapeError(f"잡코리아 목록 {page}페이지 요청 실패 (HTTP {data and data.get('status')})")
            if data.get("total") is not None:
                self.reported_total = data["total"]
            rows = [r for r in data.get("rows") or [] if r.get("gno")]
            if rows:
                seen += len(rows)
                yield [parse_row(r) for r in rows]
            if len(rows) < PAGE_SIZE or (self.reported_total is not None and page * PAGE_SIZE >= self.reported_total):
                break
            page += 1
            self.pause()
        self.check_total(seen)

    def fetch_details(self, source_ids: list[str]) -> dict[str, Detail]:
        results = self.tab.call(
            _CHECK_JS, source_ids, self.settings.detail_concurrency, timeout=30 * len(source_ids) + 30
        )
        out = {str(r["gno"]): parse_check(r) for r in results or []}
        for sid in source_ids:
            out.setdefault(sid, Detail("unknown", reason="no_result"))
        return out
