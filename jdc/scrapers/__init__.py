from .base import Scraper, ScrapeError
from .jobkorea import JobKoreaScraper
from .jobplanet import JobPlanetScraper
from .jumpit import JumpitScraper
from .remember import RememberScraper
from .wanted import WantedScraper

SCRAPERS: dict[str, type[Scraper]] = {
    cls.source: cls
    for cls in (WantedScraper, RememberScraper, JobPlanetScraper, JumpitScraper, JobKoreaScraper)
}
SOURCE_LABELS = {source: cls.label for source, cls in SCRAPERS.items()}

__all__ = ["SCRAPERS", "SOURCE_LABELS", "Scraper", "ScrapeError"]
