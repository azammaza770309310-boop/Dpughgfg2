"""SQLite access layer for CrowdCloud.

Design notes
------------
* One connection per request (stored on ``flask.g``), closed on teardown.
* WAL journal + ``busy_timeout`` so that several Gunicorn workers can
  read concurrently while writes are serialised safely.
* ``isolation_level=None`` puts the connection in autocommit mode;
  multi-statement operations use explicit ``BEGIN IMMEDIATE``.
"""

import os
import sqlite3
import time

from flask import current_app, g

# (code, prefix, name, description) - seeded on first run
SERVICES = [
    (
        "academic_advising",
        "AA",
        "Academic Advising",
        "Course selection, academic plans and study advice.",
    ),
    (
        "it_support",
        "IT",
        "IT Support",
        "Support for university accounts, email, portals and systems.",
    ),
    (
        "registration_support",
        "RS",
        "Registration Support",
        "Add/drop, schedules and registration issues.",
    ),
    (
        "student_services",
        "SS",
        "Student Services",
        "Official documents, letters and general requests.",
    ),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    id          INTEGER PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE,
    prefix      TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS service_counters (
    service_id  INTEGER PRIMARY KEY REFERENCES services(id) ON DELETE CASCADE,
    last_number INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tickets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_number TEXT NOT NULL UNIQUE,
    service_id    INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    customer_name TEXT NOT NULL DEFAULT '',
    student_id    TEXT NOT NULL DEFAULT '',
    request_text  TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'WAITING'
                  CHECK (status IN ('WAITING', 'SERVING', 'DONE', 'CANCELLED')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    called_at     TEXT,
    finished_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_tickets_service_status
    ON tickets (service_id, status);

CREATE INDEX IF NOT EXISTS idx_tickets_created
    ON tickets (created_at);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id     INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    sender        TEXT NOT NULL CHECK (sender IN ('STUDENT', 'STAFF')),
    text          TEXT NOT NULL DEFAULT '',
    file_name     TEXT NOT NULL DEFAULT '',
    stored_name   TEXT NOT NULL DEFAULT '',
    file_mime     TEXT NOT NULL DEFAULT '',
    file_size     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_ticket
    ON ticket_messages (ticket_id, id);
"""

# Kept out of SCHEMA so old databases can be migrated (ALTER) before the
# index is created - otherwise executescript would reference a missing column.
ACTIVE_STUDENT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_tickets_student_active"
    " ON tickets (service_id, student_id)"
    " WHERE status IN ('WAITING', 'SERVING')"
)


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Configure one SQLite connection for safe multi-worker access.

    ``PRAGMA journal_mode=WAL`` needs a brief exclusive moment when the
    database is not in WAL mode yet.  When several Gunicorn workers boot
    at the same time on a fresh database, this pragma can collide with
    SQLITE_BUSY — and unlike normal write locks, that particular busy is
    NOT covered by busy_timeout, so the worker would crash at boot
    (observed on GitHub Actions runners).  Retrying briefly closes the
    race window; once any single connection has switched the database to
    WAL, the pragma becomes a harmless no-op for everyone else.
    """
    conn.execute("PRAGMA busy_timeout=15000")
    for attempt in range(50):
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            break
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 49:
                raise
            time.sleep(0.1)
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")


def get_conn() -> sqlite3.Connection:
    """Return the per-request SQLite connection."""
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DB_PATH"], timeout=15)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None  # autocommit; explicit BEGIN for transactions
        _apply_pragmas(conn)
        g.db = conn
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app):
    """Register teardown and make sure the schema exists."""
    db_dir = os.path.dirname(app.config["DB_PATH"] or "")
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with app.app_context():
        init_db()
    app.teardown_appcontext(close_db)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def init_db():
    """Create tables (if missing) and seed the four services.

    Safe under the multi-worker boot race: BEGIN IMMEDIATE serialises the
    seed transaction, and INSERT OR IGNORE keeps a second worker that
    already sees rows from a crashing UNIQUE violation.

    Migration: databases created before the student-ID feature get the
    new column via ALTER TABLE, then the partial active-ticket index is
    created (kept out of executescript so old schemas never reference a
    missing column). The same applies to the chat request_text column.
    """
    conn = get_conn()
    conn.executescript(SCHEMA)
    if not _column_exists(conn, "tickets", "student_id"):
        conn.execute("ALTER TABLE tickets ADD COLUMN student_id TEXT NOT NULL DEFAULT ''")
    if not _column_exists(conn, "tickets", "request_text"):
        conn.execute("ALTER TABLE tickets ADD COLUMN request_text TEXT NOT NULL DEFAULT ''")
    conn.execute(ACTIVE_STUDENT_INDEX)
    row = conn.execute("SELECT COUNT(*) AS c FROM services").fetchone()
    if row["c"] == 0:
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(
            "INSERT OR IGNORE INTO services (code, prefix, name, description) "
            "VALUES (?, ?, ?, ?)",
            SERVICES,
        )
        conn.execute(
            "INSERT OR IGNORE INTO service_counters (service_id, last_number) "
            "SELECT id, 0 FROM services"
        )
        conn.execute("COMMIT")
