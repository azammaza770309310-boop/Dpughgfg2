"""CrowdCloud application entry point.

Run the development server:

    python run.py

Runtime environment variables (all optional):

    PORT                  HTTP port (default 5000)
    CROWDCLOUD_DB         SQLite database path
    BUSY_THRESHOLD        waiting tickets before a service is BUSY (default 8)
    HIGH_THRESHOLD        waiting tickets before a service is HIGH LOAD (default 16)
    AUTO_SERVE            1 = enable background service-clerk simulator
    AUTO_SERVE_INTERVAL   simulator tick interval in seconds (default 25)

Production (inside Docker or on a server):

    gunicorn --workers 4 --bind 0.0.0.0:5000 run:app
"""

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
