import argparse
import logging
import subprocess
import sys
import time
from datetime import date

from lendlake import bronze, transform
from lendlake.config import PROJECT_ROOT, Settings
from lendlake.dates import add_months, batch_id, month_end, month_range, parse_month
from lendlake.generator import generate_batches

log = logging.getLogger("lendlake")


class PipelineError(RuntimeError):
    pass


def _month_arg(value: str) -> date:
    try:
        return parse_month(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD or YYYY-MM, got {value!r}") from exc


def _add_window_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-date", type=_month_arg, required=True,
                        help="Business date to process; snapped to its month end (e.g. 2025-06-30)")
    parser.add_argument("--backfill-from", type=_month_arg,
                        help="Process every month from this date through --run-date")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lendlake", description="Lending analytics lakehouse pipeline")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Write synthetic source batches to the landing zone")
    _add_window_args(gen)
    gen.add_argument("--scale", type=float)
    gen.add_argument("--seed", type=int)

    ingest = sub.add_parser("ingest", help="Load landed batches into the bronze (raw) schema")
    _add_window_args(ingest)
    ingest.add_argument("--force", action="store_true", help="Reload files even if unchanged")

    build = sub.add_parser("build", help="Run dbt build (silver, snapshot, gold, tests)")
    build.add_argument("--run-date", type=_month_arg, required=True)
    build.add_argument("--full-refresh", action="store_true")
    build.add_argument("--select")

    run = sub.add_parser("run", help="generate -> ingest -> dbt build, month by month")
    _add_window_args(run)
    run.add_argument("--scale", type=float)
    run.add_argument("--seed", type=int)
    run.add_argument("--skip-generate", action="store_true", help="Use batches already in landing")

    dash = sub.add_parser("dashboard", help="Start the Streamlit dashboard")
    dash.add_argument("--port", type=int, default=8105)
    return parser


def months_to_process(args: argparse.Namespace, settings: Settings) -> list[date]:
    first = args.backfill_from or args.run_date
    if first > args.run_date:
        raise PipelineError("--backfill-from must not be after --run-date")
    if first < settings.start_month:
        raise PipelineError(f"History starts at {settings.start_month:%Y-%m}; nothing to process before it")
    return month_range(first, args.run_date)


def check_history(settings: Settings, first_month: date, run_date: date) -> None:
    """A month can only be built once the month before it has been ingested."""
    if first_month == settings.start_month:
        return
    previous = batch_id(add_months(first_month, -1))
    if previous not in bronze.ingested_batches(settings.duckdb_path):
        raise PipelineError(
            f"Batch {previous} has not been ingested. Backfill first, e.g. "
            f"python -m lendlake run --backfill-from {settings.start_month:%Y-%m-%d} "
            f"--run-date {month_end(run_date)}"
        )


def _generate(settings: Settings, months: list[date], scale: float | None, seed: int | None) -> None:
    generate_batches(
        settings.landing_dir, months[0], months[-1],
        seed=seed if seed is not None else settings.seed,
        scale=scale if scale is not None else settings.scale,
        start_month=settings.start_month,
    )


def run_pipeline(args: argparse.Namespace, settings: Settings) -> None:
    months = months_to_process(args, settings)
    check_history(settings, months[0], args.run_date)
    log.info("Processing %d month(s): %s .. %s", len(months), batch_id(months[0]), batch_id(months[-1]))
    if not args.skip_generate:
        _generate(settings, months, args.scale, args.seed)
    for month in months:
        started = time.perf_counter()
        log.info("=== Batch %s (run date %s) ===", batch_id(month), month_end(month))
        bronze.ingest_batch(settings.duckdb_path, settings.data_dir, batch_id(month))
        transform.build(settings.dbt_project_dir, settings.duckdb_path, month_end(month))
        log.info("Batch %s done in %.1fs", batch_id(month), time.perf_counter() - started)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    settings = Settings.from_env()
    try:
        if args.command == "generate":
            _generate(settings, months_to_process(args, settings), args.scale, args.seed)
        elif args.command == "ingest":
            for month in months_to_process(args, settings):
                bronze.ingest_batch(settings.duckdb_path, settings.data_dir, batch_id(month), args.force)
        elif args.command == "build":
            transform.build(settings.dbt_project_dir, settings.duckdb_path, month_end(args.run_date),
                            full_refresh=args.full_refresh, select=args.select)
        elif args.command == "run":
            run_pipeline(args, settings)
        elif args.command == "dashboard":
            app = PROJECT_ROOT / "dashboard" / "app.py"
            return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app),
                                    "--server.port", str(args.port)])
    except (PipelineError, bronze.BatchNotReady, transform.DbtError) as exc:
        log.error("%s", exc)
        return 1
    return 0
