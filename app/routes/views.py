"""HTML page routes (server-rendered first paint, then live updates via JS)."""

import os

from flask import Blueprint, current_app, render_template, request, send_from_directory

from .. import models

views_bp = Blueprint("views", __name__)


@views_bp.get("/favicon.ico")
def favicon():
    """Serve the gold cloud icon so browsers get no 404."""
    return send_from_directory(current_app.static_folder, "favicon.ico",
                               mimetype="image/x-icon")


@views_bp.get("/")
def index():
    """Service selection dashboard with live load badges."""
    return render_template(
        "index.html", services=models.list_services(), stats=models.global_stats()
    )


@views_bp.get("/ticket/<ticket_number>")
def ticket_page(ticket_number):
    ticket = models.get_ticket(ticket_number)
    if ticket is None:
        return render_template("not_found.html", ticket_number=ticket_number), 404
    return render_template("ticket.html", ticket=ticket)


@views_bp.get("/chat/<ticket_number>")
def chat_page(ticket_number):
    """Private conversation page: one ticket, one thread.

    Reached from the student's ticket page (his private link) or from the
    staff panel (?staff=1). There is no index of conversations and no
    cross-ticket access — the thread lives and dies with its ticket number.
    """
    ticket = models.get_ticket(ticket_number)
    if ticket is None:
        return render_template("not_found.html", ticket_number=ticket_number), 404
    is_staff = request.args.get("staff") == "1"
    return render_template("chat.html", ticket=ticket, is_staff=is_staff)


@views_bp.get("/uploads/<ticket_number>/<path:filename>")
def uploaded_file(ticket_number, filename):
    """Serve one chat attachment from its ticket folder.

    ``send_from_directory`` refuses path traversal, and each attachment
    carries an unguessable random prefix in its stored name, so a file
    stays reachable only through the conversation it belongs to.
    Images render inline; anything else downloads as an attachment.
    """
    folder = os.path.join(current_app.config["UPLOAD_DIR"], ticket_number)
    inline = (filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf")))
    return send_from_directory(
        folder, filename, as_attachment=not inline,
        download_name=filename.split("_", 1)[-1] if "_" in filename else filename,
    )


@views_bp.get("/queue")
def queue_board():
    """Public display board: waiting lists per service."""
    services = models.list_services()
    boards = []
    for service in services:
        boards.append(
            {
                "service": service,
                "waiting": models.list_tickets(
                    service_id=service["id"], status="WAITING",
                    limit=12, waiting_first=True,
                ),
            }
        )
    return render_template(
        "queue.html", boards=boards, stats=models.global_stats()
    )


@views_bp.get("/admin")
def admin():
    """Staff panel: call next, complete, cancel."""
    services = models.list_services()
    sections = []
    for service in services:
        sections.append(
            {
                "service": service,
                "tickets": models.list_tickets(
                    service_id=service["id"], limit=15, waiting_first=True
                ),
            }
        )
    return render_template(
        "admin.html", sections=sections, stats=models.global_stats()
    )


@views_bp.get("/healthz")
def healthz():
    """Liveness probe used by Docker / load balancers."""
    return {"status": "ok", "service": "crowdcloud"}
