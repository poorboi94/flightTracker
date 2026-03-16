"""
Shared pytest fixtures for the flight tracker test suite.
"""
import os
import sys

import pytest

# Make src/ importable without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Redirect the database to a temp file so tests never touch flights.db."""
    import database

    db_file = str(tmp_path / "test_flights.db")
    monkeypatch.setattr(database, "DB_PATH", db_file)
    database.init_db()
    return db_file


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    """Redirect the API cache to a temp directory so tests don't pollute cache/."""
    import api_client

    monkeypatch.setattr(api_client, "CACHE_DIR", str(tmp_path))
    return tmp_path
