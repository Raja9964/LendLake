import duckdb
import pytest

from lendlake.bronze import BatchNotReady, ingest_batch, ingested_batches


def _counts(db):
    with duckdb.connect(str(db), read_only=True) as con:
        return {
            t: con.execute(f"select count(*) from raw.{t}").fetchone()[0]
            for t in ("customers", "repayments", "emi_schedule", "collection_activities")
        }


def test_ingest_adds_load_metadata(tmp_path, landing):
    db = tmp_path / "wh.duckdb"
    ingest_batch(db, landing, "2024-01")
    with duckdb.connect(str(db), read_only=True) as con:
        row = con.execute(
            "select _batch_id, _source_file, _ingested_at from raw.customers limit 1"
        ).fetchone()
    assert row[0] == "2024-01"
    assert row[1] == "landing/2024-01/customers_2024-01.csv"
    assert row[2] is not None


def test_reingesting_same_batch_is_idempotent(tmp_path, landing):
    db = tmp_path / "wh.duckdb"
    ingest_batch(db, landing, "2024-01")
    ingest_batch(db, landing, "2024-02")
    before = _counts(db)
    result = ingest_batch(db, landing, "2024-02")
    assert result.loaded == {}
    assert _counts(db) == before

    forced = ingest_batch(db, landing, "2024-02", force=True)
    assert forced.loaded
    assert _counts(db) == before
    assert ingested_batches(db) == {"2024-01", "2024-02"}


def test_changed_file_replaces_rows(tmp_path, landing):
    import shutil

    data = tmp_path / "data"
    shutil.copytree(landing / "landing" / "2024-01", data / "landing" / "2024-01")
    db = tmp_path / "wh.duckdb"
    ingest_batch(db, data, "2024-01")
    csv = data / "landing" / "2024-01" / "customers_2024-01.csv"
    lines = csv.read_text().splitlines()
    csv.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(RuntimeError, match="manifest"):
        ingest_batch(db, data, "2024-01")


def test_incomplete_batch_is_rejected(tmp_path, landing):
    with pytest.raises(BatchNotReady):
        ingest_batch(tmp_path / "wh.duckdb", landing, "2031-01")
