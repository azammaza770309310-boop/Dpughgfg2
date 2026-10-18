"""Shared pytest fixtures for CrowdCloud.

Each test runs against its own temporary SQLite database so tests are
fully isolated and can be re-run in any order.
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CROWDCLOUD_DB", str(tmp_path / "crowdcloud-test.db"))
    monkeypatch.setenv("CROWDCLOUD_UPLOADS", str(tmp_path / "uploads"))
    monkeypatch.setenv("BUSY_THRESHOLD", "3")
    monkeypatch.setenv("HIGH_THRESHOLD", "6")
    monkeypatch.setenv("AUTO_SERVE", "0")
    from app import create_app

    application = create_app()
    return application


@pytest.fixture()
def client(app):
    return app.test_client()
