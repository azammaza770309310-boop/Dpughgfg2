"""Optional background thread that simulates service clerks.

Enabled with ``AUTO_SERVE=1`` (mainly for the local live demo and for
making queue movement visible without manual staff actions).  The
operations themselves are the same atomic SQL claims used by the staff
panel, so behaviour stays consistent.

When running several Gunicorn workers each worker would start its own
simulator thread and the queue would drain faster.  For that reason the
Docker/gunicorn configuration keeps AUTO_SERVE off by default; enable it
only for single-process demo runs (see README).
"""

import threading
import time


def start_auto_serve(app):
    interval = max(1, int(app.config.get("AUTO_SERVE_INTERVAL", 25)))

    def loop():
        # Give the server a moment to finish booting.
        time.sleep(1.0)
        with app.app_context():
            while True:
                time.sleep(interval)
                try:
                    from . import models

                    models.auto_serve_tick()
                except Exception:  # keep the thread alive on DB hiccups
                    app.logger.exception("auto-serve tick failed")

    thread = threading.Thread(
        target=loop, daemon=True, name="crowdcloud-auto-serve"
    )
    thread.start()
    return thread
