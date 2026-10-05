import json
from datetime import UTC, date, datetime

import duckdb
import pytest

from lendlake import cli, export
from lendlake.config import Settings

GOLD_SQL = """
create schema raw;
create schema silver;
create schema gold;
create table raw.customers as select 'C1' as customer_id union all select 'C2';
create table raw._ingestion_log as select 'x' as file;
create table silver.stg_customers as select 'C1' as customer_id;
create table gold.dim_branch as
    select * from (values ('B1', 'NORTH'), ('B2', 'SOUTH')) as t(branch_code, region);
create table gold.dim_product as select * from (values
    ('PL_SAL', 'Personal loan salaried', 'PERSONAL', false, 60),
    ('HL_STD', 'Home loan standard', 'HOME', true, 240)
) as t(product_code, product_name, product_family, is_secured, max_tenure_months);
create table gold.mart_portfolio_summary as select * from (values
    (date '2024-01-31', 'NORTH', 'HL_STD', 10, 5000000.50::decimal(18, 2), 100000::decimal(18, 2),
     0::decimal(18, 2), 10, 5000000::decimal(18, 2), 0::decimal(18, 2), 0::decimal(18, 2),
     0::decimal(18, 2), 0::decimal(18, 2)),
    (date '2024-02-29', 'NORTH', 'HL_STD', 12, 5900000::decimal(18, 2), 200000::decimal(18, 2),
     50000::decimal(18, 2), 2, 1000000::decimal(18, 2), 80000::decimal(18, 2), 76000::decimal(18, 2),
     1000::decimal(18, 2), 500::decimal(18, 2))
) as t(snapshot_month, region, product_code, active_loans, outstanding_principal, par30_principal,
       npa_principal, loans_disbursed, amount_disbursed, demand_due, collected_against_demand,
       opening_overdue, arrears_collected);
create table gold.mart_delinquency_buckets as select * from (values
    (date '2024-02-29', 'B1', 'HL_STD', 'Current', 1, 3, 4000000::decimal(18, 2)),
    (date '2024-02-29', 'B2', 'HL_STD', 'Current', 1, 2, 1000000::decimal(18, 2)),
    (date '2024-02-29', 'B1', 'HL_STD', '31-60', 3, 1, 900000::decimal(18, 2))
) as t(snapshot_month, branch_code, product_code, dpd_bucket, bucket_order, loan_count, outstanding_principal);
create table gold.mart_vintage_analysis as select * from (values
    (date '2024-01-31', 'HL_STD', 0, 10, 0),
    (date '2024-01-31', 'HL_STD', 1, 10, 1)
) as t(cohort_month, product_code, months_on_book, cohort_loans, loans_ever_30_plus);
create table gold.mart_branch_performance as select * from (values
    (date '2024-02-29', 'B1', 'Andheri', 'Mumbai', 'NORTH', 8, 4900000::decimal(18, 2), 1, 600000::decimal(18, 2),
     0.18::double, 0.0::double, 0.95::double, 0.93::double, 1),
    (date '2024-02-29', 'B2', 'Adyar', 'Chennai', 'SOUTH', 4, 1000000::decimal(18, 2), 1, 400000::decimal(18, 2),
     0.0::double, 0.0::double, 'nan'::double, 'nan'::double, 2)
) as t(snapshot_month, branch_code, branch_name, city, region, active_loans, outstanding_principal,
       loans_disbursed, amount_disbursed, par30_ratio, gnpa_ratio, current_collection_efficiency,
       overall_collection_efficiency, collection_rank);
"""

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.fixture
def warehouse(tmp_path):
    path = tmp_path / "wh.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute(GOLD_SQL)
    return path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(payload):
    return [dict(zip(payload["columns"], row, strict=True)) for row in payload["rows"]]


def test_export_writes_each_mart_as_compact_json(warehouse, tmp_path):
    out = tmp_path / "site" / "data"
    manifest = export.export_site(warehouse, out, now=NOW)

    assert sorted(p.name for p in out.iterdir()) == [
        "branches.json", "dpd.json", "manifest.json", "products.json", "summary.json", "vintage.json",
    ]
    summary = read(out / "summary.json")
    assert summary["source"] == "gold.mart_portfolio_summary"
    first = rows(summary)[0]
    assert first["month"] == "2024-01-31"
    assert first["product"] == "HL_STD"
    assert first["outstanding_principal"] == 5000000.5
    assert manifest["datasets"]["summary"] == {
        "file": "data/summary.json", "source": "gold.mart_portfolio_summary", "rows": 2,
        "bytes": (out / "summary.json").stat().st_size,
    }


def test_dpd_is_rolled_up_to_region(warehouse, tmp_path):
    export.export_site(warehouse, tmp_path, now=NOW)
    dpd = rows(read(tmp_path / "dpd.json"))
    assert [(r["region"], r["bucket"], r["loans"], r["outstanding_principal"]) for r in dpd] == [
        ("NORTH", "Current", 3, 4000000.0),
        ("NORTH", "31-60", 1, 900000.0),
        ("SOUTH", "Current", 2, 1000000.0),
    ]


def test_products_put_home_loans_first(warehouse, tmp_path):
    export.export_site(warehouse, tmp_path, now=NOW)
    assert [p["product"] for p in rows(read(tmp_path / "products.json"))] == ["HL_STD", "PL_SAL"]


def test_nan_ratios_become_null(warehouse, tmp_path):
    export.export_site(warehouse, tmp_path, now=NOW)
    text = (tmp_path / "branches.json").read_text(encoding="utf-8")
    assert "NaN" not in text
    adyar = next(r for r in rows(json.loads(text)) if r["branch_code"] == "B2")
    assert adyar["overall_collection_efficiency"] is None


def test_manifest_describes_the_run(warehouse, tmp_path, monkeypatch):
    for key in ("GITHUB_SHA", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
        monkeypatch.delenv(key, raising=False)
    manifest = export.export_site(warehouse, tmp_path, now=NOW)

    assert read(tmp_path / "manifest.json") == manifest
    assert manifest["built_at"] == "2026-01-02T03:04:05Z"
    assert (manifest["first_month"], manifest["run_date"], manifest["months"]) == ("2024-01-31", "2024-02-29", 2)
    assert manifest["layers"]["bronze"] == {"tables": 1, "rows": 2}
    assert manifest["layers"]["silver"] == {"tables": 1, "rows": 1}
    assert manifest["layers"]["gold"]["tables"] == 6
    assert "raw._ingestion_log" not in manifest["tables"]
    assert manifest["dbt"] is None and manifest["simulation"] is None and manifest["ci"] is None


def test_manifest_picks_up_dbt_results_simulation_and_ci(warehouse, tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    results = [
        {"unique_id": "model.lendlake.mart_a", "status": "success"},
        {"unique_id": "seed.lendlake.products", "status": "success"},
        {"unique_id": "snapshot.lendlake.snap_customers", "status": "success"},
        {"unique_id": "test.lendlake.unique_a", "status": "pass"},
        {"unique_id": "test.lendlake.not_null_a", "status": "pass"},
    ]
    (target / "run_results.json").write_text(json.dumps({
        "metadata": {"dbt_version": "1.11.15"},
        "args": {"vars": {"run_date": "2024-02-29"}},
        "results": results,
    }), encoding="utf-8")
    landing = tmp_path / "landing"
    for batch in ("2024-01", "2024-02"):
        (landing / batch).mkdir(parents=True)
        (landing / batch / "_manifest.json").write_text(json.dumps({"seed": 42, "scale": 0.2}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_SHA", "0123456789abcdef")
    monkeypatch.setenv("GITHUB_REPOSITORY", "Raja9964/LendLake")
    monkeypatch.setenv("GITHUB_RUN_ID", "99")

    manifest = export.export_site(warehouse, tmp_path / "data", dbt_target=target, landing_dir=landing, now=NOW)

    assert manifest["dbt"] == {
        "version": "1.11.15", "run_date": "2024-02-29", "models": 1, "snapshots": 1, "seeds": 1,
        "tests": 2, "tests_passed": 2,
    }
    assert manifest["simulation"] == {"seed": 42, "scale": 0.2, "batches": 2}
    assert manifest["ci"] == {
        "commit": "0123456",
        "commit_url": "https://github.com/Raja9964/LendLake/commit/0123456789abcdef",
        "run_url": "https://github.com/Raja9964/LendLake/actions/runs/99",
    }


def test_missing_warehouse_is_an_export_error(tmp_path):
    with pytest.raises(export.ExportError, match="Run the pipeline first"):
        export.export_site(tmp_path / "nope.duckdb", tmp_path / "data")


def test_missing_marts_are_an_export_error(tmp_path):
    path = tmp_path / "empty.duckdb"
    duckdb.connect(str(path)).close()
    with pytest.raises(export.ExportError, match="Gold marts are missing"):
        export.export_site(path, tmp_path / "data")


def test_empty_marts_are_an_export_error(warehouse, tmp_path):
    with duckdb.connect(str(warehouse)) as con:
        con.execute("delete from gold.mart_portfolio_summary")
    with pytest.raises(export.ExportError, match="empty"):
        export.export_site(warehouse, tmp_path / "data")


def test_cli_export_site(warehouse, tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path / "nodata", duckdb_path=warehouse, dbt_project_dir=tmp_path,
        seed=42, scale=0.2, start_month=date(2024, 1, 1),
    )
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls: settings))
    assert cli.build_parser().parse_args(["export-site"]).out == export.SITE_DATA_DIR

    assert cli.main(["export-site", "--out", str(tmp_path / "out")]) == 0
    assert read(tmp_path / "out" / "manifest.json")["months"] == 2

    monkeypatch.setattr(cli.Settings, "from_env", classmethod(
        lambda cls: Settings(**{**settings.__dict__, "duckdb_path": tmp_path / "missing.duckdb"})))
    assert cli.main(["export-site", "--out", str(tmp_path / "out")]) == 1
