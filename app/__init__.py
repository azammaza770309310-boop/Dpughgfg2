"""CrowdCloud Flask application factory."""

import os

from flask import Flask

from .config import get_config


def create_app(config_override=None):
    """Create and configure the CrowdCloud application.

    Templates and static files live at the project root (outside the
    ``app`` package) to keep the layout required by the course project.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    app = Flask(
        __name__,
        template_folder=os.path.join(project_root, "templates"),
        static_folder=os.path.join(project_root, "static"),
    )
    app.config.update(get_config())
    if config_override:
        app.config.update(config_override)

    # chat attachments live here (uploads/<ticket_number>/...)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    from .db import init_app as init_db_app

    init_db_app(app)

    from .routes.api import api_bp
    from .routes.views import views_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    if app.config.get("AUTO_SERVE"):
        from .auto_serve import start_auto_serve

        start_auto_serve(app)

    return app
