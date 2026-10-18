"""Regression test for the multi-worker boot race (GitHub Actions incident).

Symptom fixed: when several Gunicorn workers import the app at the same
time on a FRESH database, ``PRAGMA journal_mode=WAL`` can raise
``sqlite3.OperationalError: database is locked`` — that particular busy
is not covered by busy_timeout — and the worker crashed at boot
(see CI run logs; gunicorn exits with WORKER_BOOT_ERROR).

The fix retries the journal-mode pragma briefly and makes seeding
idempotent.  These tests simulate the race directly with threads.
"""

import os
import sqlite3
import threading
import time

import pytest


def test_concurrent_app_boot_on_fresh_database(tmp_path, monkeypatch):
    """8 threads create the app simultaneously on the same fresh DB."""
    db_path = tmp_path / "race.db"
    monkeypatch.setenv("CROWDCLOUD_DB", str(db_path))
    monkeypatch.setenv("BUSY_THRESHOLD", "8")
    monkeypatch.setenv("HIGH_THRESHOLD", "16")
    monkeypatch.setenv("AUTO_SERVE", "0")

    from app import create_app

    errors = []
    barrier = threading.Barrier(8)

    def boot():
        try:
            barrier.wait()  # maximise the chance all threads collide at once
            create_app()
        except Exception as exc:  # noqa: BLE001 - record any boot failure
            errors.append(exc)

    threads = [threading.Thread(target=boot) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, f"concurrent boot failed: {errors!r}"

    # exactly one seeded set of services, WAL mode active
    conn = sqlite3.connect(db_path)
    services = conn.execute("SELECT COUNT(*) FROM services").fetchone()[0]
    counters = conn.execute("SELECT COUNT(*) FROM service_counters").fetchone()[0]
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert services == 4
    assert counters == 4
    assert mode.lower() == "wal"


def test_wal_pragma_retry_survives_transient_busy(tmp_path):
    """_apply_pragmas retries a 'database is locked' failure instead of raising."""

    class FlakyConn:
        """Proxy around a real connection; fails the first WAL attempts."""

        def __init__(self, real, fail_times):
            self._real = real
            self._fail_times = fail_times
            self.failed = 0

        def execute(self, sql, *args, **kwargs):
            if "journal_mode" in sql and self.failed < self._fail_times:
                self.failed += 1
                raise sqlite3.OperationalError("database is locked")
            return self._real.execute(sql, *args, **kwargs)

    from app.db import _apply_pragmas

    real = sqlite3.connect(tmp_path / "retry.db")
    conn = FlakyConn(real, fail_times=2)
    start = time.monotonic()
    _apply_pragmas(conn)  # must not raise
    elapsed = time.monotonic() - start
    mode = real.execute("PRAGMA journal_mode").fetchone()[0]
    real.close()

    assert conn.failed == 2          # both simulated failures were absorbed
    assert elapsed >= 0.2            # backed off between attempts (2 x 0.1 s)
    assert mode.lower() == "wal"     # and the real database is in WAL mode
