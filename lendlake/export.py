"""Export the Gold marts as JSON for the static dashboard in site/."""

import json
import logging
import math
import os
import re
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb

from lendlake.config import PROJECT_ROOT

log = logging.getLogger(__name__)

SITE_DATA_DIR = PROJECT_ROOT / "site" / "data"
LAYERS = {"raw": "bronze", "silver": "silver", "snapshots": "silver", "gold": "gold"}

# Each dataset is one Gold mart, trimmed to what the dashboard reads.
DATASETS = {
    "summary": ("gold.mart_portfolio_summary", """
        select snapshot_month as month, region, product_code as product, active_loans,
               outstanding_principal, par30_principal, npa_principal, loans_disbursed, amount_disbursed,
               demand_due, collected_against_demand, opening_overdue, arrears_collected
        from gold.mart_portfolio_summary
        order by month, region, product
    """),
    "dpd": ("gold.mart_delinquency_buckets", """
        select d.snapshot_month as month, b.region, d.product_code as product, d.dpd_bucket as bucket,
               d.bucket_order, sum(d.loan_count) as loans, sum(d.outstanding_principal) as outstanding_principal
        from gold.mart_delinquency_buckets as d
        inner join gold.dim_branch as b using (branch_code)
        group by all
        order by month, region, product, bucket_order
    """),
    "vintage": ("gold.mart_vintage_analysis", """
        select cohort_month, product_code as product, months_on_book, cohort_loans, loans_ever_30_plus
        from gold.mart_vintage_analysis
        order by cohort_month, product, months_on_book
    """),
    "branches": ("gold.mart_branch_performance", """
        select snapshot_month as month, branch_code, branch_name, city, region, active_loans,
               outstanding_principal, loans_disbursed, amount_disbursed, par30_ratio, gnpa_ratio,
               current_collection_efficiency, overall_collection_efficiency, collection_rank
        from gold.mart_branch_performance
        order by month, collection_rank, branch_code
    """),
    "products": ("gold.dim_product", """
        select product_code as product, product_name, product_family, is_secured
        from gold.dim_product
        -- home loans first, longest tenure first within a family
        order by product_family, max_tenure_months desc
    """),
}


class ExportError(RuntimeError):
    pass


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float):
        return None if math.isnan(value) else round(value, 6)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _write_json(path: Path, payload: dict) -> int:
    text = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def _table_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    tables = con.execute(
        "select schema_name, table_name from duckdb_tables() "
        "where schema_name in ('raw', 'silver', 'snapshots', 'gold') and not starts_with(table_name, '_') "
        "order by schema_name, table_name"
    ).fetchall()
    return {
        f"{schema}.{table}": con.execute(f'select count(*) from "{schema}"."{table}"').fetchone()[0]
        for schema, table in tables
    }


def _layers(counts: dict[str, int]) -> dict[str, dict]:
    layers = {name: {"tables": 0, "rows": 0} for name in ("bronze", "silver", "gold")}
    for relation, rows in counts.items():
        layer = layers[LAYERS[relation.split(".")[0]]]
        layer["tables"] += 1
        layer["rows"] += rows
    return layers


def _dbt_summary(target_dir: Path | None) -> dict | None:
    path = target_dir / "run_results.json" if target_dir else None
    if not path or not path.exists():
        return None
    results = json.loads(path.read_text(encoding="utf-8"))
    kinds = Counter(r["unique_id"].split(".")[0] for r in results["results"])
    tests = [r for r in results["results"] if r["unique_id"].startswith("test.")]
    return {
        "version": results["metadata"].get("dbt_version"),
        "run_date": (results.get("args") or {}).get("vars", {}).get("run_date"),
        "models": kinds["model"],
        "snapshots": kinds["snapshot"],
        "seeds": kinds["seed"],
        "tests": len(tests),
        "tests_passed": sum(r["status"] == "pass" for r in tests),
    }


def _simulation(landing_dir: Path | None) -> dict | None:
    if not landing_dir or not landing_dir.exists():
        return None
    batches = sorted(p for p in landing_dir.iterdir() if re.fullmatch(r"\d{4}-\d{2}", p.name))
    manifests = [p / "_manifest.json" for p in batches if (p / "_manifest.json").exists()]
    if not manifests:
        return None
    meta = json.loads(manifests[-1].read_text(encoding="utf-8"))
    return {"seed": meta.get("seed"), "scale": meta.get("scale"), "batches": len(manifests)}


def _ci_context() -> dict | None:
    sha, repo, run_id = (os.getenv(k) for k in ("GITHUB_SHA", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    if not (sha and repo and run_id):
        return None
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    return {
        "commit": sha[:7],
        "commit_url": f"{server}/{repo}/commit/{sha}",
        "run_url": f"{server}/{repo}/actions/runs/{run_id}",
    }


def export_site(db_path: Path, data_dir: Path, *, dbt_target: Path | None = None,
                landing_dir: Path | None = None, now: datetime | None = None) -> dict:
    if not db_path.exists():
        raise ExportError(f"No warehouse at {db_path}. Run the pipeline first.")

    data_dir.mkdir(parents=True, exist_ok=True)
    datasets = {}
    with duckdb.connect(str(db_path), read_only=True) as con:
        try:
            for name, (source, sql) in DATASETS.items():
                cursor = con.execute(sql)
                columns = [c[0] for c in cursor.description]
                rows = [[_plain(v) for v in row] for row in cursor.fetchall()]
                size = _write_json(data_dir / f"{name}.json", {"source": source, "columns": columns, "rows": rows})
                datasets[name] = {"file": f"data/{name}.json", "source": source, "rows": len(rows), "bytes": size}
            first, last, months = con.execute(
                "select min(snapshot_month), max(snapshot_month), count(distinct snapshot_month) "
                "from gold.mart_portfolio_summary"
            ).fetchone()
            counts = _table_counts(con)
        except duckdb.CatalogException as exc:
            raise ExportError(f"Gold marts are missing from {db_path}. Run the pipeline first. ({exc})") from exc
    if not months:
        raise ExportError("The Gold marts are empty. Run the pipeline first.")

    manifest = {
        "built_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "first_month": _plain(first),
        "run_date": _plain(last),
        "months": months,
        "datasets": datasets,
        "layers": _layers(counts),
        "tables": counts,
        "dbt": _dbt_summary(dbt_target),
        "simulation": _simulation(landing_dir),
        "ci": _ci_context(),
    }
    _write_json(data_dir / "manifest.json", manifest)
    log.info("Wrote %d datasets to %s, run date %s", len(datasets), data_dir, manifest["run_date"])
    return manifest
