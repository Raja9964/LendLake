from datetime import date

import pytest

from lendlake.generator import generate_batches

START = date(2024, 1, 1)


@pytest.fixture(scope="session")
def landing(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("data")
    generate_batches(data_dir / "landing", START, date(2024, 6, 1), seed=7, scale=0.2, start_month=START)
    return data_dir
