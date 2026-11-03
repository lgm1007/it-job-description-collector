"""Data shapes shared by the scrapers, the pipeline and the database layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Posting:
    """One job posting as a scraper saw it in a site's listing."""

    source: str
    source_id: str
    url: str
    title: str
    company: str
    locations: list[str] = field(default_factory=list)  # raw, e.g. ["서울 강남구"]
    career_min: int | None = None  # years; 0 = 신입 가능
    career_max: int | None = None  # None = 상한 없음
    career_text: str | None = None  # the site's own wording, used when min/max are unknown
    skills: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)  # 직무명, e.g. "백엔드"
    employment_type: str | None = None
    deadline: str | None = None  # YYYY-MM-DD, inclusive; None = 상시/채용시 마감
    posted_at: str | None = None  # YYYY-MM-DD
    description: str | None = None
    is_open: bool = True
    extra: dict = field(default_factory=dict)


DetailState = Literal["open", "closed", "missing", "unknown"]


@dataclass
class Detail:
    """Result of looking up a single posting's detail page.

    `fields` holds Posting attribute names to merge into the stored row. A key that is
    present with None (e.g. deadline) means the site explicitly has no value.
    """

    state: DetailState
    fields: dict = field(default_factory=dict)
    reason: str | None = None
