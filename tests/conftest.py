from __future__ import annotations

from pathlib import Path

import pytest

from src.database.sqlite import initialize_database


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    initialize_database(db_path)
    return db_path
