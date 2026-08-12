"""Shared fixtures for CHANGE X tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from changex.app import db


@pytest.fixture()
def tmp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "test.db"
        monkeypatch.setattr(db, "DB_PATH", path)
        db.init_db(path)
        db.reset_lock_stats()
        db.set_failure_hook(None)
        yield path


@pytest.fixture()
def client(tmp_db, monkeypatch):
    from changex.app import main as main_mod

    monkeypatch.setattr(main_mod, "_RATE", {})
    main_mod.REQUEST_LOGS.clear()
    from changex.app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def load_client(tmp_db, monkeypatch):
    """TestClient with rate limiting disabled for load profiles."""
    from changex.app import main as main_mod

    monkeypatch.setattr(main_mod, "_RATE", {})
    monkeypatch.setattr(main_mod, "_rate_limit", lambda *a, **k: None)
    main_mod.REQUEST_LOGS.clear()
    from changex.app.main import app

    with TestClient(app) as c:
        yield c
