"""Runtime configuration, resolved when the app is created.

Every value can be overridden with an environment variable so that the
same image can run in development, in Docker and during load testing
without code changes.
"""

import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def get_config() -> dict:
    """Return the effective configuration dict for the application."""

    return {
        "SECRET_KEY": os.environ.get("SECRET_KEY", "crowdcloud-dev-key"),
        # SQLite database location (Docker mounts a volume on /data)
        "DB_PATH": os.environ.get(
            "CROWDCLOUD_DB",
            os.path.join(BASE_DIR, "database", "crowdcloud.db"),
        ),
        # Load-status thresholds: number of WAITING tickets per service
        "BUSY_THRESHOLD": _int_env("BUSY_THRESHOLD", 8),
        "HIGH_THRESHOLD": _int_env("HIGH_THRESHOLD", 16),
        # Optional background simulator ("service clerk")
        "AUTO_SERVE": _bool_env("AUTO_SERVE", False),
        "AUTO_SERVE_INTERVAL": _int_env("AUTO_SERVE_INTERVAL", 25),
        # Explicit assumption used for the estimated waiting time
        "AVG_SERVICE_MINUTES": _int_env("AVG_SERVICE_MINUTES", 2),
        # Private student<->staff chat: where attachments are stored and
        # how big one uploaded file may be.
        "UPLOAD_DIR": os.environ.get(
            "CROWDCLOUD_UPLOADS",
            os.path.join(BASE_DIR, "uploads"),
        ),
        "MAX_UPLOAD_MB": _int_env("MAX_UPLOAD_MB", 8),
    }
