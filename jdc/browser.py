"""A dedicated Chrome driven through browser-harness.

browser-harness talks to Chrome over CDP through a small local daemon. We point it at a
Chrome we launch ourselves (separate profile, fixed remote-debugging port) rather than the
user's everyday browser, so the daily job never waits on an "Allow remote debugging?"
prompt and never touches personal tabs.

Scrapers open one tab per site and call that site's own JSON endpoints with `fetch()`
from inside the page: requests go out from a real browser on the site's origin, with its
cookies, which is what the sites' own front-ends do.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from .config import Settings

log = logging.getLogger(__name__)

_MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_UNIX_CHROMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
_WIN_CHROMES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)

# In-page request runner: a small promise pool so detail lookups can overlap a little.
_FETCH_POOL_JS = """
(async (reqs, concurrency, timeoutMs) => {
  const one = async (r) => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(r.url, {
        method: r.method || 'GET', headers: r.headers || {}, body: r.body ?? undefined,
        credentials: r.credentials || 'same-origin', signal: ctrl.signal,
      });
      return {status: res.status, url: res.url, text: await res.text()};
    } catch (e) {
      return {status: 0, url: r.url, text: '', error: String(e)};
    } finally {
      clearTimeout(timer);
    }
  };
  const out = new Array(reqs.length);
  let next = 0;
  const worker = async () => { while (next < reqs.length) { const i = next++; out[i] = await one(reqs[i]); } };
  await Promise.all(Array.from({length: Math.min(concurrency, reqs.length)}, worker));
  return out;
})
"""


class BrowserError(RuntimeError):
    pass


def configure_harness_env(settings: Settings) -> None:
    """Point browser-harness at our Chrome. Must run before browser_harness is imported."""
    os.environ["BU_CDP_URL"] = settings.cdp_url
    os.environ["BU_NAME"] = "jdc"
    os.environ.setdefault("BH_HOME", str(settings.data_dir / "browser-harness"))
    if os.name != "nt":
        # AF_UNIX socket paths are capped at 104 bytes on macOS; keep the daemon socket short.
        os.environ.setdefault("BH_RUNTIME_DIR", f"/tmp/jdc-bh-{os.getuid()}")
    os.environ.setdefault("BH_TELEMETRY", "0")
    os.environ.setdefault("BH_TAB_MARKER", "0")


def find_chrome(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if sys.platform == "darwin" and Path(_MAC_CHROME).exists():
        return _MAC_CHROME
    if os.name == "nt":
        for path in _WIN_CHROMES:
            if Path(path).exists():
                return path
    for name in _UNIX_CHROMES:
        if found := shutil.which(name):
            return found
    raise BrowserError("Chrome을 찾지 못했습니다. JDC_CHROME_PATH에 실행 파일 경로를 지정하세요.")


def cdp_version(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as res:
            return json.loads(res.read())
    except (OSError, ValueError):
        return None


def _desktop_user_agent(binary: str) -> str | None:
    """Headless Chrome announces itself as HeadlessChrome; present a regular desktop UA instead."""
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if not (m := re.search(r"(\d+)\.\d+\.\d+", out)):
        return None
    platform_token = {
        "darwin": "Macintosh; Intel Mac OS X 10_15_7",
        "win32": "Windows NT 10.0; Win64; x64",
    }.get(sys.platform, "X11; Linux x86_64")
    return (
        f"Mozilla/5.0 ({platform_token}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{m.group(1)}.0.0.0 Safari/537.36"
    )


class Browser:
    """Context manager: ensures our Chrome and the browser-harness daemon are up."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._chrome: subprocess.Popen | None = None
        self._h = None  # browser_harness.helpers, imported lazily after env setup
        self._tab: Tab | None = None

    def __enter__(self) -> "Browser":
        configure_harness_env(self.settings)
        self._ensure_chrome()
        from browser_harness import admin, helpers

        admin.ensure_daemon(wait=60)
        self._h = helpers
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def h(self):
        if self._h is None:
            raise BrowserError("Browser is not started")
        return self._h

    def _ensure_chrome(self) -> None:
        port = self.settings.cdp_port
        if cdp_version(port):
            log.info("Chrome already listening on CDP port %s; reusing it", port)
            return
        binary = find_chrome(self.settings.chrome_path)
        profile = self.settings.chrome_profile_dir
        profile.mkdir(parents=True, exist_ok=True)
        args = [
            binary,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--lang=ko-KR",
            "--window-size=1440,900",
        ]
        if self.settings.headless:
            args.append("--headless=new")
            if ua := _desktop_user_agent(binary):
                args.append(f"--user-agent={ua}")
        args.append("about:blank")
        log_path = self.settings.data_dir / "chrome.log"
        with open(log_path, "ab") as sink:
            self._chrome = subprocess.Popen(
                args, stdout=sink, stderr=sink, stdin=subprocess.DEVNULL, start_new_session=True
            )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if cdp_version(port):
                log.info("launched Chrome (pid %s) on CDP port %s", self._chrome.pid, port)
                return
            if self._chrome.poll() is not None:
                break
            time.sleep(0.3)
        raise BrowserError(f"Chrome이 CDP 포트 {port}에서 응답하지 않습니다. {log_path}를 확인하세요.")

    def open(self, url: str) -> "Tab":
        """Point the working tab at `url`.

        One tab is reused for every site, as browser-harness recommends: closing a tab
        makes the daemon re-attach its session, and a navigation sent meanwhile is lost.
        """
        if self._tab is None:
            target_id = self.h.new_tab(url)
            self.h.wait_for_load(timeout=30)
            self._tab = Tab(self, target_id)
        else:
            self._tab.goto(url)
        return self._tab

    def close(self) -> None:
        if self._tab is not None:
            self._tab.close()
            self._tab = None
        if self._chrome is None or not self.settings.close_browser:
            return
        # The daemon holds a CDP connection to the Chrome we are about to stop.
        try:
            from browser_harness import admin

            admin.restart_daemon()
        except Exception as e:  # noqa: BLE001 - best effort shutdown
            log.warning("stopping browser-harness daemon failed: %s", e)
        self._chrome.terminate()
        try:
            self._chrome.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._chrome.kill()
        self._chrome = None


class Tab:
    """One browser-harness tab pinned to a site; runs JavaScript and fetches inside it."""

    def __init__(self, browser: Browser, target_id: str):
        self.browser = browser
        self.target_id = target_id

    @property
    def h(self):
        return self.browser.h

    def _activate(self) -> None:
        if self.h.current_tab()["targetId"] != self.target_id:
            self.h.switch_tab(self.target_id)

    def goto(self, url: str) -> None:
        self._activate()
        self.h.goto_url(url)
        self.h.wait_for_load(timeout=30)

    def evaluate(self, expression: str, timeout: float = 60) -> Any:
        """Evaluate an expression (awaiting promises) and return its JSON value."""
        self._activate()
        response = self.h.cdp(
            "Runtime.evaluate",
            _response_timeout=timeout + 10,
            expression=expression,
            returnByValue=True,
            awaitPromise=True,
        )
        if details := response.get("exceptionDetails"):
            exc = details.get("exception") or {}
            raise BrowserError(f"page script failed: {exc.get('description') or details.get('text')}")
        return response.get("result", {}).get("value")

    def call(self, function_source: str, *args: Any, timeout: float = 60) -> Any:
        """Run `(function_source)(...args)` in the page; args are passed as JSON."""
        rendered = ", ".join(json.dumps(a, ensure_ascii=False) for a in args)
        return self.evaluate(f"({function_source})({rendered})", timeout=timeout)

    def fetch_many(self, requests: list[dict], concurrency: int = 1, timeout: float = 30) -> list[dict]:
        """Fetch each {url, method?, headers?, body?} from the page; returns {status, url, text}."""
        if not requests:
            return []
        rounds = -(-len(requests) // max(1, concurrency))
        return self.call(
            _FETCH_POOL_JS, requests, concurrency, int(timeout * 1000), timeout=timeout * rounds + 10
        )

    def fetch(self, url: str, *, method: str = "GET", body: str | None = None,
              headers: dict | None = None, timeout: float = 30) -> dict:
        return self.fetch_many([{"url": url, "method": method, "body": body, "headers": headers or {}}],
                               timeout=timeout)[0]

    def fetch_json(self, url: str, **kwargs) -> tuple[int, Any]:
        res = self.fetch(url, **kwargs)
        return res["status"], parse_json(res.get("text"))

    def close(self) -> None:
        try:
            self.h.close_tab(self.target_id)
        except Exception as e:  # noqa: BLE001 - tab may already be gone
            log.debug("closing tab %s failed: %s", self.target_id, e)


def parse_json(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None
