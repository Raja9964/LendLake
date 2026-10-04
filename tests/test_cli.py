from datetime import date
from types import SimpleNamespace

import pytest

from lendlake import cli
from lendlake.config import Settings


@pytest.fixture
def settings(tmp_path, landing):
    return Settings(
        data_dir=landing, duckdb_path=tmp_path / "wh.duckdb", dbt_project_dir=tmp_path,
        seed=7, scale=0.05, start_month=date(2024, 1, 1),
    )


def test_run_date_is_snapped_to_month():
    args = cli.build_parser().parse_args(["build", "--run-date", "2025-06-30"])
    assert args.run_date == date(2025, 6, 1)


def test_invalid_run_date_is_rejected():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["build", "--run-date", "30/06/2025"])


def test_backfill_window(settings):
    args = SimpleNamespace(run_date=date(2024, 4, 1), backfill_from=date(2024, 2, 1))
    assert cli.months_to_process(args, settings) == [date(2024, 2, 1), date(2024, 3, 1), date(2024, 4, 1)]
    with pytest.raises(cli.PipelineError):
        cli.months_to_process(SimpleNamespace(run_date=date(2024, 1, 1), backfill_from=date(2024, 3, 1)), settings)


def test_missing_history_fails_fast(settings):
    with pytest.raises(cli.PipelineError, match="2024-02 has not been ingested"):
        cli.check_history(settings, date(2024, 3, 1), date(2024, 3, 1))


def test_run_orders_steps_month_by_month(settings, monkeypatch):
    calls = []
    monkeypatch.setattr(cli.transform, "build", lambda project, db, run_date: calls.append(("build", run_date)))
    real_ingest = cli.bronze.ingest_batch

    def ingest(db, data_dir, batch):
        calls.append(("ingest", batch))
        return real_ingest(db, data_dir, batch)

    monkeypatch.setattr(cli.bronze, "ingest_batch", ingest)
    args = SimpleNamespace(run_date=date(2024, 2, 1), backfill_from=date(2024, 1, 1),
                           skip_generate=True, scale=None, seed=None)
    cli.run_pipeline(args, settings)
    assert calls == [
        ("ingest", "2024-01"), ("build", date(2024, 1, 31)),
        ("ingest", "2024-02"), ("build", date(2024, 2, 29)),
    ]


def test_main_returns_error_code_on_pipeline_error(monkeypatch, settings):
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls: settings))
    assert cli.main(["run", "--run-date", "2024-03-31", "--skip-generate"]) == 1
