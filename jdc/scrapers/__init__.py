from .base import Scraper, ScrapeError
from .jobkorea import JobKoreaScraper
from .jobplanet import JobPlanetScraper
from .jumpit import JumpitScraper
from .remember import RememberScraper
from .saramin import SaraminScraper
from .wanted import WantedScraper

SCRAPERS: dict[str, type[Scraper]] = {
    cls.source: cls
    for cls in (WantedScraper, RememberScraper, JobPlanetScraper, JumpitScraper, SaraminScraper, JobKoreaScraper)
}

__all__ = ["SCRAPERS", "Scraper", "ScrapeError"]
