"""Bronze layer: land raw batch files in DuckDB, untyped, with load metadata."""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

log = logging.getLogger(__name__)

RAW_SCHEMA = "raw"
JSON_TABLES = {"branches": "array", "collection_activities": "newline_delimited"}


class BatchNotReady(RuntimeError):
    pass


@dataclass
class IngestResult:
    batch_id: str
    loaded: dict[str, int]
    skipped: list[str]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _reader(table: str, path: Path) -> str:
    literal = "'" + path.as_posix().replace("'", "''") + "'"
    if table in JSON_TABLES:
        return f"(select json as payload from read_json_objects({literal}, format='{JSON_TABLES[table]}'))"
    return f"read_csv({literal}, header=true, all_varchar=true, delim=',', quote='\"', escape='\"')"


def _ensure_log(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"create schema if not exists {RAW_SCHEMA}")
    con.execute(f"""
        create table if not exists {RAW_SCHEMA}._ingestion_log (
            batch_id varchar, table_name varchar, source_file varchar primary key,
            file_sha256 varchar, row_count bigint, ingested_at timestamp
        )
    """)


def ingested_batches(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set()
    with duckdb.connect(str(db_path), read_only=True) as con:
        exists = con.execute(
            "select count(*) from information_schema.tables "
            "where table_schema = ? and table_name = '_ingestion_log'", [RAW_SCHEMA]
        ).fetchone()[0]
        if not exists:
            return set()
        return {r[0] for r in con.execute(f"select distinct batch_id from {RAW_SCHEMA}._ingestion_log").fetchall()}


def ingest_batch(db_path: Path, data_dir: Path, batch_id: str, force: bool = False) -> IngestResult:
    batch_dir = data_dir / "landing" / batch_id
    manifest_path = batch_dir / "_manifest.json"
    if not manifest_path.exists():
        raise BatchNotReady(f"No complete batch at {batch_dir} (missing _manifest.json)")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    db_path.parent.mkdir(parents=True, exist_ok=True)
    loaded, skipped = {}, []
    ingested_at = datetime.now(UTC).replace(tzinfo=None)
    with duckdb.connect(str(db_path)) as con:
        _ensure_log(con)
        for entry in manifest["files"]:
            table, path = entry["table"], batch_dir / entry["file"]
            source_file = path.relative_to(data_dir).as_posix()
            checksum = _sha256(path)
            seen = con.execute(
                f"select file_sha256 from {RAW_SCHEMA}._ingestion_log where source_file = ?", [source_file]
            ).fetchone()
            if seen and seen[0] == checksum and not force:
                skipped.append(table)
                continue
            loaded[table] = _load_file(con, table, path, batch_id, source_file, checksum, ingested_at)
            if loaded[table] != entry["rows"]:
                raise RuntimeError(f"{source_file}: loaded {loaded[table]} rows, manifest says {entry['rows']}")
    log.info("Bronze %s: loaded %s, skipped %s unchanged file(s)",
             batch_id, sum(loaded.values()), len(skipped))
    return IngestResult(batch_id, loaded, skipped)


def _load_file(con, table: str, path: Path, batch_id: str, source_file: str,
               checksum: str, ingested_at: datetime) -> int:
    target = f"{RAW_SCHEMA}.{_quote(table)}"
    reader = _reader(table, path)
    columns = [row[0] for row in con.execute(f"describe select * from {reader}").fetchall()]

    con.execute("begin transaction")
    try:
        con.execute(f"""
            create table if not exists {target} as
            select *, ''::varchar as _batch_id, ''::varchar as _source_file,
                   null::timestamp as _ingested_at
            from {reader} limit 0
        """)
        existing = {row[0] for row in con.execute(f"describe {target}").fetchall()}
        for column in columns:
            if column not in existing:
                # tolerate additive schema drift; older rows just get nulls
                con.execute(f"alter table {target} add column {_quote(column)} varchar")
        # Replacing by source file is what makes re-runs idempotent.
        con.execute(f"delete from {target} where _source_file = ?", [source_file])
        con.execute(
            f"insert into {target} by name "
            f"select *, ? as _batch_id, ? as _source_file, ? as _ingested_at from {reader}",
            [batch_id, source_file, ingested_at],
        )
        rows = con.execute(f"select count(*) from {target} where _source_file = ?", [source_file]).fetchone()[0]
        con.execute(f"delete from {RAW_SCHEMA}._ingestion_log where source_file = ?", [source_file])
        con.execute(
            f"insert into {RAW_SCHEMA}._ingestion_log values (?, ?, ?, ?, ?, ?)",
            [batch_id, table, source_file, checksum, rows, ingested_at],
        )
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise
    return rows
