import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from lendlake.dates import parse_month

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    duckdb_path: Path
    dbt_project_dir: Path
    seed: int
    scale: float
    start_month: date

    @property
    def landing_dir(self) -> Path:
        return self.data_dir / "landing"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env")
        return cls(
            data_dir=_path(os.getenv("LENDLAKE_DATA_DIR", "data")),
            duckdb_path=_path(os.getenv("LENDLAKE_DUCKDB_PATH", "warehouse/lendlake.duckdb")),
            dbt_project_dir=PROJECT_ROOT / "transform",
            seed=int(os.getenv("LENDLAKE_SEED", "42")),
            scale=float(os.getenv("LENDLAKE_SCALE", "1.0")),
            start_month=parse_month(os.getenv("LENDLAKE_START_MONTH", "2024-01")),
        )
