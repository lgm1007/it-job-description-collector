"""Command line entry point: `jdc scrape`, `jdc serve`, `jdc stats`."""
from __future__ import annotations

import argparse
import logging
import sys

from . import db
from .config import ALL_SOURCES, load_settings
from .normalize import today_kst


def _print_summaries(summaries: list[dict]) -> None:
    print(f"\n{'사이트':<10}{'상태':<9}{'목록':>7}{'신규':>7}{'재오픈':>7}{'마감':>7}{'상세':>7}{'재확인':>7}")
    for s in summaries:
        print(f"{s['source']:<10}{s['status']:<9}{s.get('listed', 0):>7}{s.get('new', 0):>7}"
              f"{s.get('reopened', 0):>7}{s.get('closed', 0):>7}{s.get('details', 0):>7}{s.get('verified', 0):>7}")
        if s.get("error"):
            print(f"  ! {s['error']}")


def _stats(settings) -> None:
    conn = db.connect(settings.db_path)
    today = today_kst()
    rows = conn.execute(
        f"SELECT source, SUM({db.VISIBLE}) AS visible, SUM(status = 'closed') AS closed, COUNT(*) AS total "
        "FROM jobs GROUP BY source ORDER BY source",
        {"today": today},
    ).fetchall()
    print(f"{'사이트':<10}{'노출 중':>8}{'마감':>8}{'전체':>8}")
    for r in rows:
        print(f"{r['source']:<10}{r['visible'] or 0:>8}{r['closed'] or 0:>8}{r['total']:>8}")
    print("\n최근 수집:")
    for run in db.latest_runs(conn):
        print(f"  {run['source']:<10} {run['status']:<8} {run['started_at']}  목록 {run['listed']}  "
              f"신규 {run['new']}  마감 {run['closed']}" + (f"  ! {run['error']}" if run["error"] else ""))
    conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jdc", description="국내 개발자 채용공고 수집기")
    sub = parser.add_subparsers(dest="command", required=True)

    scrape = sub.add_parser("scrape", help="지금 채용공고를 수집합니다")
    scrape.add_argument("--source", action="append", choices=ALL_SOURCES, help="특정 사이트만 (여러 번 지정 가능)")
    scrape.add_argument("--no-details", action="store_true", help="새 공고의 상세 정보를 가져오지 않습니다")

    serve = sub.add_parser("serve", help="웹 서버를 띄우고 매일 자동 수집합니다")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--no-scheduler", action="store_true", help="자동 수집 없이 웹 서버만")

    sub.add_parser("stats", help="저장된 공고 현황")
    sub.add_parser("reindex", help="지역·검색어·중복 판단을 저장된 데이터로 다시 계산합니다 (정규화 규칙을 바꾼 뒤)")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()

    if args.command == "scrape":
        from .pipeline import AlreadyRunning, run_scrape

        try:
            summaries = run_scrape(settings, args.source, details=not args.no_details)
        except AlreadyRunning as e:
            print(e, file=sys.stderr)
            return 2
        _print_summaries(summaries)
        return 1 if any(s["status"] == "failed" for s in summaries) else 0

    if args.command == "serve":
        import uvicorn

        from .api import create_app

        app = create_app(settings, scheduler=not args.no_scheduler)
        uvicorn.run(app, host=args.host or settings.host, port=args.port or settings.port)
        return 0

    if args.command == "reindex":
        conn = db.connect(settings.db_path)
        print(f"{db.rederive(conn)}건을 다시 계산했습니다")
        conn.close()
        return 0

    _stats(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
