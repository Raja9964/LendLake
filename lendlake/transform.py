"""Thin wrapper around dbt's programmatic runner."""

import json
import logging
import os
from datetime import date
from pathlib import Path

from dbt.cli.main import dbtRunner

log = logging.getLogger(__name__)


class DbtError(RuntimeError):
    pass


def _invoke(project_dir: Path, db_path: Path, args: list[str]) -> None:
    os.environ["LENDLAKE_DUCKDB_PATH"] = str(db_path)
    command = [*args, "--project-dir", str(project_dir), "--profiles-dir", str(project_dir)]
    result = dbtRunner().invoke(command)
    if not result.success:
        raise DbtError(f"dbt {args[0]} failed")


def ensure_packages(project_dir: Path, db_path: Path) -> None:
    if not (project_dir / "dbt_packages" / "dbt_utils").exists():
        log.info("Installing dbt packages")
        _invoke(project_dir, db_path, ["deps"])


def build(project_dir: Path, db_path: Path, run_date: date, full_refresh: bool = False,
          select: str | None = None) -> None:
    ensure_packages(project_dir, db_path)
    args = ["build", "--vars", json.dumps({"run_date": run_date.isoformat()})]
    if full_refresh:
        args.append("--full-refresh")
    if select:
        args += ["--select", select]
    log.info("dbt build for run_date=%s", run_date)
    _invoke(project_dir, db_path, args)
