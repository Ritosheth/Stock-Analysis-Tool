from __future__ import annotations

import argparse
from datetime import date, datetime, time
from pathlib import Path
import sys

from .akshare_client import AkshareHistoryProvider
from .cache import DailyBarCache
from .futu_client import FutuAShareClient
from .history import CachedHistoryProvider
from .pipeline import run_daily_pipeline
from .tushare_client import TushareHistoryProvider
from .validation import pick_next_bars, read_daily_records_csv, validate_next_day, write_validation_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate A-share daily limit-up and turnover review from Futu OpenAPI.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Trade date, for example 2026-06-14.")
    parser.add_argument("--output-dir", default="outputs/daily", help="Directory for CSV reports.")
    parser.add_argument("--host", default="127.0.0.1", help="Futu OpenD host.")
    parser.add_argument("--port", default=11111, type=int, help="Futu OpenD port.")
    parser.add_argument("--turnover-limit", default=30, type=int, help="Number of turnover leaders to include.")
    parser.add_argument("--cache-dir", default="data/cache", help="Directory for local K-line cache.")
    parser.add_argument(
        "--history-source",
        choices=["auto", "futu", "tushare", "akshare"],
        default="auto",
        help="History K-line source. auto prefers TuShare when TUSHARE_TOKEN is configured, then AkShare.",
    )
    parser.add_argument("--tushare-token", help="TuShare token. If omitted, TUSHARE_TOKEN is used.")
    parser.add_argument(
        "--evidence-source",
        choices=["auto", "local", "futu", "cninfo", "eastmoney", "news", "billboard", "none"],
        default="auto",
        help="Reason evidence source. auto uses local reasons, Futu, CNINFO, Eastmoney news/billboard, then suspected-rule fallback.",
    )
    parser.add_argument("--no-html-report", action="store_true", help="Do not generate the synchronized HTML review report.")
    parser.add_argument("--no-forum-search", action="store_true", help="Do not search public forums for discussion summaries.")
    parser.add_argument("--validate-report", help="Validate an existing daily review CSV with next-day K-line data.")
    parser.add_argument("--next-date", help="Next trading date for validation, for example 2026-06-15.")
    args = parser.parse_args()

    if args.validate_report:
        if not args.next_date:
            parser.error("--next-date is required with --validate-report")
        records = read_daily_records_csv(Path(args.validate_report))
        cache = DailyBarCache(Path(args.cache_dir))
        primary, fallback = _history_sources(args.history_source, args.tushare_token, futu_client=None)
        provider = CachedHistoryProvider(cache=cache, primary_provider=primary, fallback_provider=fallback)
        history = {record.code: provider.get_history(record.code, days=10, end=date.fromisoformat(args.next_date)) for record in records}
        next_bars = pick_next_bars(records, history, args.next_date)
        rows = validate_next_day(records, next_bars)
        output_path = Path(args.output_dir) / ("%s-next-day-validation.csv" % args.next_date)
        write_validation_csv(rows, output_path)
        if not rows:
            print(
                "Warning: generated 0 validation rows. Check whether --next-date is a completed trading day and K-line data is available.",
                file=sys.stderr,
            )
        print("Generated %s validation rows: %s" % (len(rows), output_path))
        return 0

    trade_date = date.fromisoformat(args.date)
    if _should_skip_intraday_review(trade_date):
        note_path = _write_skip_note(
            trade_date=trade_date,
            output_dir=Path(args.output_dir),
            reason="A股尚未收盘，当前仅为盘中时点，跳过正式每日复盘生成以避免误导。",
        )
        print("Skipped daily review generation: %s" % note_path, file=sys.stderr)
        return 0

    client = FutuAShareClient(host=args.host, port=args.port)
    try:
        primary, fallback = _history_sources(args.history_source, args.tushare_token, futu_client=client)
        history_provider = CachedHistoryProvider(
            cache=DailyBarCache(Path(args.cache_dir)),
            primary_provider=primary,
            fallback_provider=fallback,
        )
        result = run_daily_pipeline(
            client=client,
            trade_date=trade_date,
            output_dir=Path(args.output_dir),
            turnover_limit=args.turnover_limit,
            cache_dir=Path(args.cache_dir),
            history_provider=history_provider,
            evidence_source=args.evidence_source,
            generate_html_report=not args.no_html_report,
            forum_search_enabled=not args.no_forum_search,
        )
    finally:
        client.close()

    print("Generated %s rows: %s" % (len(result.records), result.output_path))
    if result.report_path:
        print("Generated HTML report: %s" % result.report_path)
    if result.report_warning:
        print("Warning: %s" % result.report_warning, file=sys.stderr)
    return 0


def _should_skip_intraday_review(trade_date: date) -> bool:
    if trade_date != date.today():
        return False
    return datetime.now().time() < time(15, 5)


def _write_skip_note(trade_date: date, output_dir: Path, reason: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    note_path = output_dir / ("%s-run-notes.md" % trade_date.isoformat())
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    note_path.write_text(
        "\n".join(
            [
                "# %s 每日复盘运行说明" % trade_date.isoformat(),
                "",
                "- 生成状态：",
                "  - 已跳过正式 CSV/HTML 日报生成。",
                "- 跳过原因：",
                "  - %s" % reason,
                "- 当前时间：",
                "  - `%s CST`" % timestamp,
                "- 处理原则：",
                "  - 收盘前不产出正式每日复盘，避免将盘中行情误当作收盘结论。",
                "- 下一步：",
                "  - 请在 15:05 CST 之后重新运行同一命令生成正式日报。",
            ]
        ),
        encoding="utf-8",
    )
    return note_path

def _history_sources(history_source: str, tushare_token: str | None, futu_client):
    if history_source == "futu":
        if futu_client is None:
            raise ValueError("--history-source futu is not available during report validation")
        return futu_client, AkshareHistoryProvider()
    if history_source == "tushare":
        return TushareHistoryProvider(tushare_token), AkshareHistoryProvider()
    if history_source == "akshare":
        return AkshareHistoryProvider(), None

    try:
        return TushareHistoryProvider(tushare_token), AkshareHistoryProvider()
    except ValueError:
        if futu_client is not None:
            return futu_client, AkshareHistoryProvider()
        return AkshareHistoryProvider(), None


if __name__ == "__main__":
    raise SystemExit(main())
