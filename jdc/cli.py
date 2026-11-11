"""Command line entry point: `jdc scrape`, `jdc sync`, `jdc stats`."""
from __future__ import annotations

import argparse
import logging
import sys

from . import db
from .config import ALL_SOURCES, load_settings
from .normalize import today_kst


def _print_summaries(summaries: list[dict]) -> None:
    print(f"\n{'사이트':<10}{'상태':<9}{'목록':>7}{'신규':>7}{'마감 삭제':>9}{'상세':>7}{'재확인':>7}")
    for s in summaries:
        print(f"{s['source']:<10}{s['status']:<9}{s.get('listed', 0):>7}{s.get('new', 0):>7}"
              f"{s.get('closed', 0):>9}{s.get('details', 0):>7}{s.get('verified', 0):>7}")
        if s.get("error"):
            print(f"  ! {s['error']}")


def _stats(settings) -> None:
    conn = db.connect(settings.db_path)
    today = today_kst()
    rows = conn.execute(
        f"SELECT source, SUM({db.VISIBLE}) AS visible, COUNT(*) AS total FROM jobs GROUP BY source ORDER BY source",
        {"today": today},
    ).fetchall()
    # 'stored' also counts postings whose deadline passed since the last scrape; the next one deletes them.
    print(f"{'사이트':<10}{'노출 중':>8}{'저장':>8}")
    for r in rows:
        print(f"{r['source']:<10}{r['visible'] or 0:>8}{r['total']:>8}")
    print("\n최근 수집:")
    for run in db.latest_runs(conn):
        print(f"  {run['source']:<10} {run['status']:<8} {run['started_at']}  목록 {run['listed']}  "
              f"신규 {run['new']}  마감 삭제 {run['closed']}" + (f"  ! {run['error']}" if run["error"] else ""))
    conn.close()


def _sync(settings, *, force: bool = False) -> int:
    from .pipeline import AlreadyRunning
    from .sync import SyncError, run_sync

    try:
        result = run_sync(settings, force=force)
    except (SyncError, AlreadyRunning) as e:
        print(e, file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - usually the network; the scrape's results are safe in SQLite
        print(f"Supabase 업로드에 실패했습니다: {e}\n수집 결과는 로컬에 있으니 `python -m jdc sync`로 다시 올리면 됩니다.",
              file=sys.stderr)
        return 1
    print(f"\nSupabase 업로드: 신규·변경 {result.uploaded:,}건, 삭제 {result.deleted:,}건 (전체 {result.total:,}건)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jdc", description="국내 개발자 채용공고 수집기")
    sub = parser.add_subparsers(dest="command", required=True)

    scrape = sub.add_parser("scrape", help="지금 채용공고를 수집합니다")
    scrape.add_argument("--source", action="append", choices=ALL_SOURCES, help="특정 사이트만 (여러 번 지정 가능)")
    scrape.add_argument("--no-details", action="store_true", help="새 공고의 상세 정보를 가져오지 않습니다")
    scrape.add_argument("--no-sync", action="store_true", help="끝난 뒤 Supabase에 올리지 않습니다")

    sync = sub.add_parser("sync", help="로컬의 공고를 Supabase에 올립니다 (scrape가 끝나면 자동으로 실행됩니다)")
    sync.add_argument("--force", action="store_true", help="공고 대부분을 지우게 되더라도 진행합니다")

    grant = sub.add_parser("grant", help="Supabase 계정에 공고 조회 권한을 줍니다")
    grant.add_argument("email")

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
        code = 1 if any(s["status"] == "failed" for s in summaries) else 0
        if settings.supabase_db_url and not args.no_sync:
            code = _sync(settings) or code
        return code

    if args.command == "sync":
        return _sync(settings, force=args.force)

    if args.command == "grant":
        from .sync import SyncError, grant_viewer

        try:
            granted = grant_viewer(settings, args.email)
        except SyncError as e:
            print(e, file=sys.stderr)
            return 2
        except Exception as e:  # noqa: BLE001 - usually the network or the connection string
            print(f"Supabase에 연결하지 못했습니다: {e}", file=sys.stderr)
            return 1
        if not granted:
            print(f"{args.email} 계정이 없습니다. Supabase 대시보드의 Authentication에서 먼저 만들어 주세요.", file=sys.stderr)
            return 1
        print(f"{args.email} 계정이 공고를 볼 수 있습니다")
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
