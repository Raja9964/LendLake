import hashlib
import json
from datetime import date

import pandas as pd
import yaml

from lendlake.config import PROJECT_ROOT
from lendlake.generator import generate_batches
from lendlake.generator.simulation import BOUNCE_CHARGE, LATE_FEE_RATE, amortization
from tests.conftest import START


def _digest(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def test_batches_are_complete(landing):
    for batch in ("2024-01", "2024-02", "2024-03", "2024-04"):
        manifest = json.loads((landing / "landing" / batch / "_manifest.json").read_text())
        assert {f["table"] for f in manifest["files"]} >= {"customers", "repayments", "emi_schedule"}


def test_same_seed_is_reproducible_and_horizon_independent(tmp_path, landing):
    generate_batches(tmp_path, START, date(2024, 2, 1), seed=7, scale=0.2, start_month=START)
    assert _digest(tmp_path / "2024-02") == _digest(landing / "landing" / "2024-02")


def test_scale_changes_volume(tmp_path):
    generate_batches(tmp_path / "a", START, START, seed=1, scale=0.05, start_month=START)
    generate_batches(tmp_path / "b", START, START, seed=1, scale=0.3, start_month=START)
    small = pd.read_csv(tmp_path / "a" / "2024-01" / "loan_applications_2024-01.csv")
    large = pd.read_csv(tmp_path / "b" / "2024-01" / "loan_applications_2024-01.csv")
    assert len(large) > 3 * len(small)


def test_injects_data_quality_issues(landing):
    customers = pd.concat(
        pd.read_csv(p, dtype=str) for p in (landing / "landing").glob("*/customers_*.csv")
    )
    assert customers.duplicated().any()
    assert customers["date_of_birth"].str.contains("/").any()
    assert customers["city"].str.contains("Bangalore|Bombay|Gurgaon|Madras", regex=True).any()


def test_late_arriving_repayments(landing):
    late = 0
    for batch in ("2024-02", "2024-03", "2024-04", "2024-05", "2024-06"):
        df = pd.read_csv(landing / "landing" / batch / f"repayments_{batch}.csv", dtype=str)
        iso = df["payment_date"][df["payment_date"].str.match(r"^\d{4}-\d{2}-\d{2}$")]
        late += int((iso.str[:7] < batch).sum())
    assert late > 0


def test_amortization_principal_adds_up():
    schedule = amortization(250_000, 14.5, 36)
    assert sum(row[3] for row in schedule) == 250_000 * 100
    assert schedule[-1][1] - schedule[-1][3] == 0


def test_penalty_policy_matches_dbt_vars():
    project = yaml.safe_load((PROJECT_ROOT / "transform" / "dbt_project.yml").read_text())
    assert project["vars"]["late_fee_rate"] == LATE_FEE_RATE
    assert project["vars"]["bounce_charge"] == BOUNCE_CHARGE
