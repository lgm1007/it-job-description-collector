"""Runtime settings, read from JDC_* environment variables (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALL_SOURCES = ("wanted", "remember", "jobplanet", "jumpit", "saramin", "jobkorea")


def load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, existing environment wins."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env(name: str, default: str) -> str:
    return os.environ.get(f"JDC_{name}", default).strip()


def _bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    sources: tuple[str, ...]
    chrome_path: str | None
    cdp_port: int
    headless: bool
    close_browser: bool
    request_delay: float
    detail_concurrency: int
    max_details: int
    verify_limit: int
    # Postings missing from a complete listing whose detail check is inconclusive
    # are closed after this many consecutive runs.
    missing_runs_to_close: int = 3
    # Where finished scrapes are uploaded for the web app; None keeps everything local.
    supabase_db_url: str | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobs.sqlite3"

    @property
    def chrome_profile_dir(self) -> Path:
        return self.data_dir / "chrome-profile"

    @property
    def cdp_url(self) -> str:
        return f"http://127.0.0.1:{self.cdp_port}"

    @property
    def lock_path(self) -> Path:
        return self.data_dir / "scrape.lock"


def load_settings() -> Settings:
    load_dotenv()
    data_dir = Path(_env("DATA_DIR", ".data"))
    if not data_dir.is_absolute():
        data_dir = PROJECT_ROOT / data_dir
    sources = tuple(s.strip() for s in _env("SOURCES", ",".join(ALL_SOURCES)).split(",") if s.strip())
    unknown = set(sources) - set(ALL_SOURCES)
    if unknown:
        raise ValueError(f"알 수 없는 JDC_SOURCES 값: {', '.join(sorted(unknown))}")
    return Settings(
        data_dir=data_dir,
        sources=sources,
        chrome_path=_env("CHROME_PATH", "") or None,
        cdp_port=int(_env("CDP_PORT", "9333")),
        headless=_bool("HEADLESS", True),
        close_browser=_bool("CLOSE_BROWSER", True),
        request_delay=float(_env("REQUEST_DELAY", "0.7")),
        detail_concurrency=max(1, int(_env("DETAIL_CONCURRENCY", "3"))),
        max_details=int(_env("MAX_DETAILS", "6000")),
        verify_limit=int(_env("VERIFY_LIMIT", "600")),
        supabase_db_url=_env("SUPABASE_DB_URL", "") or None,
    )
