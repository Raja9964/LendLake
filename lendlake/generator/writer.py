import json
import logging
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from lendlake.dates import batch_id, month_end, month_range
from lendlake.generator import messiness
from lendlake.generator.reference import BRANCHES
from lendlake.generator.simulation import LendingSimulator

log = logging.getLogger(__name__)

COLUMNS = {
    "customers": [
        "customer_id", "first_name", "last_name", "gender", "date_of_birth", "mobile", "email", "pan",
        "city", "state", "pincode", "employment_type", "annual_income", "credit_score", "kyc_status",
        "created_at", "updated_at",
    ],
    "loan_applications": [
        "application_id", "customer_id", "branch_code", "product_code", "application_date",
        "requested_amount", "requested_tenure_months", "channel", "application_status",
        "decision_date", "rejection_reason", "updated_at",
    ],
    "sanctions": [
        "sanction_id", "application_id", "loan_id", "sanction_date", "sanctioned_amount",
        "interest_rate", "tenure_months", "emi_amount",
    ],
    "disbursements": [
        "disbursement_id", "loan_id", "disbursement_date", "disbursed_amount", "processing_fee",
        "disbursement_mode", "bank_reference",
    ],
    "emi_schedule": [
        "loan_id", "installment_no", "due_date", "opening_principal", "emi_amount",
        "principal_component", "interest_component", "closing_principal",
    ],
    "repayments": [
        "payment_id", "loan_id", "installment_no", "payment_date", "amount_paid", "penalty_paid",
        "payment_mode", "payment_status", "bounce_reason",
    ],
    "collection_activities": [
        "activity_id", "loan_id", "activity_ts", "activity_type", "outcome", "agent", "ptp",
    ],
}


def _branch_master(month: date) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "branch_code": b.code, "branch_name": b.name, "city": b.city, "state": b.state,
            "region": b.region, "branch_type": b.branch_type, "opened_on": b.opened_on.isoformat(),
        }
        for b in BRANCHES if b.opened_on <= month_end(month)
    ])


def _write_batch(batch_dir: Path, month: date, frames: dict[str, pd.DataFrame], meta: dict) -> dict:
    tmp_dir = batch_dir.with_name(batch_dir.name + ".tmp")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True)
    tag = batch_id(month)
    files = []
    for table, df in frames.items():
        if table == "branches":
            name = f"branches_{tag}.json"
            (tmp_dir / name).write_text(json.dumps(df.to_dict("records"), indent=1), encoding="utf-8")
        elif table == "collection_activities":
            name = f"collection_activities_{tag}.jsonl"
            lines = (json.dumps(r) for r in df.to_dict("records"))
            (tmp_dir / name).write_text("\n".join(lines) + ("\n" if len(df) else ""), encoding="utf-8")
        else:
            name = f"{table}_{tag}.csv"
            df.to_csv(tmp_dir / name, index=False, lineterminator="\n")
        files.append({"table": table, "file": name, "rows": len(df)})

    manifest = {"batch_id": tag, **meta, "files": files}
    # The manifest goes in last; ingestion treats a batch without it as incomplete.
    (tmp_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    shutil.rmtree(batch_dir, ignore_errors=True)
    tmp_dir.rename(batch_dir)
    return manifest


def generate_batches(
    landing_dir: Path, first: date, last: date, *, seed: int, scale: float, start_month: date
) -> list[Path]:
    sim = LendingSimulator(seed=seed, scale=scale, start_month=start_month)
    rows = sim.run(until=last.replace(day=1), emit_from=first.replace(day=1))
    tables = {
        name: pd.DataFrame(rows.get(name, []), columns=[*columns, "_arrival"])
        for name, columns in COLUMNS.items()
    }

    written = []
    for month in month_range(first, last):
        rng = np.random.default_rng([seed, month.year, month.month, 99])
        frames = {"branches": messiness.apply("branches", _branch_master(month), rng)}
        for name, df in tables.items():
            batch = df[df["_arrival"] == month].drop(columns="_arrival")
            frames[name] = messiness.apply(name, batch.reset_index(drop=True), rng)
        if month >= date(2024, 7, 1) and len(frames["repayments"]):
            # schema drift: the payments system started sending a reference column mid-2024
            frames["repayments"]["channel_reference"] = np.where(
                frames["repayments"]["payment_mode"].str.strip().str.upper().isin(["UPI", "NEFT"]),
                [f"REF{n:010d}" for n in rng.integers(0, 10**10, len(frames["repayments"]))], "",
            )
        batch_dir = landing_dir / batch_id(month)
        manifest = _write_batch(batch_dir, month, frames, {"seed": seed, "scale": scale})
        total = sum(f["rows"] for f in manifest["files"])
        log.info("Generated batch %s (%s rows across %s files)", batch_id(month), total, len(frames))
        written.append(batch_dir)
    return written
