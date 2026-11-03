"""Common scraper plumbing: open the site in a tab, page through listings, look up details."""
from __future__ import annotations

import logging
import random
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urlparse

from ..browser import BrowserError, parse_json
from ..models import Detail, Posting

if TYPE_CHECKING:
    from ..browser import Tab
    from ..config import Settings

log = logging.getLogger(__name__)


class ScrapeError(RuntimeError):
    pass


def sections(*pairs: tuple[str, object]) -> str | None:
    """Join titled description blocks, skipping empty ones."""
    parts = []
    for heading, body in pairs:
        if isinstance(body, str) and body.strip():
            text = body.replace("\r\n", "\n").strip()
            parts.append(f"[{heading}]\n{text}")
    return "\n\n".join(parts) or None


class Scraper:
    source: ClassVar[str]
    label: ClassVar[str]
    home_url: ClassVar[str]
    # True when the listing lacks description/skills/dates and new postings need a detail lookup.
    enrich_with_details: ClassVar[bool] = True
    detail_batch: ClassVar[int] = 24
    # Seconds between requests for sites that rate-limit harder than JDC_REQUEST_DELAY allows.
    min_interval: ClassVar[float] = 0.0
    # Cap on unlisted postings re-checked per run (None = JDC_VERIFY_LIMIT).
    max_verify: ClassVar[int | None] = None

    def __init__(self, tab: "Tab", settings: "Settings"):
        self.tab = tab
        self.settings = settings
        # Set by iter_listing(): True only if every page was read and the totals add up.
        self.listing_complete = False
        self.reported_total: int | None = None

    # -- lifecycle -----------------------------------------------------------------
    def prepare(self) -> None:
        """Make sure the tab sits on the site's origin before in-page fetches run."""
        host = urlparse(self.home_url).hostname
        started = time.monotonic()
        renavigated = False
        while time.monotonic() - started < 40:
            try:
                if self.tab.evaluate("location.hostname") == host and self.tab.evaluate("document.readyState") != "loading":
                    time.sleep(1.0)  # let first-party cookies/scripts settle
                    return
            except BrowserError:
                pass
            if not renavigated and time.monotonic() - started > 10:
                log.info("%s: page did not load, navigating again", self.source)
                renavigated = True
                try:
                    self.tab.goto(self.home_url)
                except Exception as e:  # noqa: BLE001 - the loop decides whether we got there
                    log.warning("%s: re-navigation failed: %s", self.source, e)
            time.sleep(0.5)
        raise ScrapeError(f"{self.label} 페이지({self.home_url})를 열지 못했습니다")

    # -- to implement --------------------------------------------------------------
    def iter_listing(self) -> Iterator[list[Posting]]:
        raise NotImplementedError

    def fetch_details(self, source_ids: list[str]) -> dict[str, Detail]:
        raise NotImplementedError

    # -- helpers -------------------------------------------------------------------
    def pause(self) -> None:
        delay = max(self.settings.request_delay, self.min_interval)
        time.sleep(delay + random.uniform(0, delay / 2))

    # A rate-limited request often comes back without CORS headers, which the page sees
    # as status 0 ("Failed to fetch"); limits seen in practice lift within a minute or two.
    RETRY_WAITS = (5, 20, 45, 90)

    def get_json(self, url: str, *, method: str = "GET", body: str | None = None,
                 headers: dict | None = None):
        """Fetch JSON from inside the page, backing off on rate limits and transient errors."""
        last = None
        for wait in (*self.RETRY_WAITS, None):
            res = self.tab.fetch(url, method=method, body=body, headers=headers)
            status = res["status"]
            data = parse_json(res.get("text"))
            if status == 200 and data is not None:
                return data
            last = f"HTTP {status} {res.get('error') or (res.get('text') or '')[:120]}"
            if status in (401, 404) or wait is None:
                break
            log.info("%s: %s, retrying in %ss", self.source, last, wait)
            time.sleep(wait)
        raise ScrapeError(f"{self.label} 요청 실패: {url} ({last})")

    def get_many(self, requests: list[dict]) -> list[dict]:
        return self.tab.fetch_many(requests, concurrency=self.settings.detail_concurrency)

    def check_total(self, seen: int) -> None:
        """A listing counts as complete only if we saw (almost) everything the site reported."""
        if self.reported_total is None:
            self.listing_complete = True
            return
        self.listing_complete = seen >= self.reported_total * 0.9
        if not self.listing_complete:
            log.warning("%s: saw %d of %d reported postings", self.source, seen, self.reported_total)
