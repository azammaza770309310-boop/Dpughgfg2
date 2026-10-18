"""REST API blueprint.

JSON endpoints used by the web UI, by curl smoke-tests, by the demo
scenario script and by the load-testing tool.  Keeping the API separate
from the HTML pages is what makes realistic benchmarking possible:
load tools exercise the same code path a real client uses.

This build adds the private student<->staff chat endpoints:

* ``GET  /api/tickets/<n>/messages``   - read the thread (needs the
  ticket number, which only the student and the staff panel have).
* ``POST /api/tickets/<n>/messages``   - send a message and/or an
  attachment (image or file). The STUDENT side is rejected with 403
  (``reason: not_your_turn``) until the ticket is being served.
"""

import os
import re
import uuid

from flask import Blueprint, current_app, jsonify, request

from .. import models
from ..load_status import LEVELS

api_bp = Blueprint("api", __name__, url_prefix="/api")

# never trust the client filename: keep only safe characters
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _save_attachment(ticket, upload) -> dict:
    """Store one uploaded file under uploads/<ticket_number>/ and describe it.

    Raises ValueError with a user-facing message when the file is not
    acceptable (empty, too large, unsafe name).
    """
    if upload is None or not upload.filename:
        raise ValueError("no file")
    original = os.path.basename(upload.filename).strip()
    if not original:
        raise ValueError("invalid file name")
    safe = _SAFE_NAME.sub("_", original)[:120] or "file"
    max_bytes = current_app.config["MAX_UPLOAD_MB"] * 1024 * 1024

    # FileStorage seeks are cheap enough for the size cap we enforce below;
    # reading the stream is required to persist it anyway.
    data = upload.read()
    if not data:
        raise ValueError("empty file")
    if len(data) > max_bytes:
        raise ValueError(
            f"file too large (max {current_app.config['MAX_UPLOAD_MB']} MB)"
        )

    stored_name = f"{uuid.uuid4().hex}_{safe}"
    folder = os.path.join(current_app.config["UPLOAD_DIR"], ticket["ticket_number"])
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, stored_name), "wb") as fh:
        fh.write(data)
    return {
        "file_name": original,
        "stored_name": stored_name,
        "file_mime": (upload.mimetype or "application/octet-stream")[:100],
        "file_size": len(data),
    }


def _error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _resolve_service(payload):
    """Find a service from JSON body keys (id or code)."""
    if payload is None:
        return None
    service_id = payload.get("service_id")
    service_code = payload.get("service_code") or payload.get("service")
    if service_id is not None:
        return models.get_service(service_id)
    if service_code:
        return models.get_service(str(service_code).strip().lower())
    return None


# --------------------------------------------------------------- services


@api_bp.get("/services")
def get_services():
    """All services with live queue stats and load level."""
    return jsonify({"services": models.list_services(), "stats": models.global_stats()})


@api_bp.get("/stats")
def get_stats():
    """Global counters and overall load level."""
    return jsonify(models.global_stats())


@api_bp.post("/services/<identifier>/next")
def call_next(identifier):
    """Staff action: call the next waiting customer of a service."""
    service = models.get_service(identifier)
    if service is None:
        return _error("service not found", 404)
    ticket = models.call_next(service["id"])
    if ticket is None:
        return jsonify({"message": "no waiting tickets", "ticket": None})
    return jsonify({"ticket": ticket})


# --------------------------------------------------------------- tickets


@api_bp.post("/tickets")
def create_ticket():
    """Issue a new queue ticket.

    Body (JSON or form): {"service_code": "it_support", "customer_name": "Ali",
                          "student_id": "441002357"}
    ``student_id`` is optional (name-only tickets stay valid for scripts and
    load tests). When provided and the student already holds an active
    ticket for the same service, returns 409 with the existing ticket.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict()
    if not any(k in payload for k in ("service_code", "service", "service_id")):
        return _error("a valid 'service_code' or 'service_id' is required", 400)
    service = _resolve_service(payload)
    if service is None:
        return _error("service not found", 404)
    customer_name = (payload.get("customer_name") or "").strip()
    student_id = (payload.get("student_id") or "").strip()
    request_text = (payload.get("request_text") or "").strip()
    try:
        ticket = models.create_ticket(
            service["id"], customer_name, student_id, request_text
        )
    except models.DuplicateActiveTicket as exc:
        existing = str(exc)
        return (
            jsonify(
                {
                    "error": "this student_id already has an active ticket "
                    f"for {service['name']}: {existing}",
                    "ticket": existing,
                }
            ),
            409,
        )
    except Exception:
        return _error("could not create ticket, please retry", 500)
    if ticket is None:
        return _error("service not found", 404)
    return jsonify({"ticket": ticket, "service": service}), 201


@api_bp.get("/tickets")
def get_tickets():
    """List tickets. Filters: ?service_code=it_support&status=WAITING&limit=50"""
    service = None
    identifier = request.args.get("service_code") or request.args.get("service_id")
    if identifier:
        service = models.get_service(identifier)
        if service is None:
            return _error("service not found", 404)
    status = request.args.get("status", "").strip().upper() or None
    if status and status not in models.TICKET_STATUSES:
        return _error(f"invalid status, expected one of {models.TICKET_STATUSES}", 400)
    try:
        limit = min(500, max(1, int(request.args.get("limit", 50))))
    except ValueError:
        limit = 50
    tickets = models.list_tickets(
        service_id=service["id"] if service else None,
        status=status,
        limit=limit,
        waiting_first=bool(request.args.get("waiting_first")),
    )
    return jsonify({"tickets": tickets, "count": len(tickets)})


@api_bp.get("/tickets/<ticket_number>")
def get_ticket(ticket_number):
    """One ticket with live position, estimated wait and service load."""
    ticket = models.get_ticket(ticket_number)
    if ticket is None:
        return _error("ticket not found", 404)
    return jsonify({"ticket": ticket})


@api_bp.post("/tickets/<ticket_number>/status")
def set_ticket_status(ticket_number):
    """Staff action: change ticket status (SERVING / DONE / CANCELLED)."""
    payload = request.get_json(silent=True) or request.form.to_dict()
    new_status = (payload.get("status") or "").strip().upper()
    if new_status not in models.TICKET_STATUSES:
        return _error(f"invalid status, expected one of {models.TICKET_STATUSES}", 400)
    try:
        ticket = models.update_ticket_status(ticket_number, new_status)
    except ValueError as exc:
        return _error(str(exc), 409)
    if ticket is None:
        return _error("ticket not found", 404)
    return jsonify({"ticket": ticket})


@api_bp.post("/tickets/<ticket_number>/cancel")
def cancel_ticket(ticket_number):
    """Customer action: cancel a waiting ticket."""
    try:
        ticket = models.cancel_ticket(ticket_number)
    except ValueError as exc:
        return _error(str(exc), 409)
    if ticket is None:
        return _error("ticket not found", 404)
    return jsonify({"ticket": ticket})


# ---------------------------------------------------------------- chat


def _chat_ticket_or_404(ticket_number):
    ticket = models.get_ticket(ticket_number)
    if ticket is None:
        return None, _error("ticket not found", 404)
    return ticket, None


@api_bp.get("/tickets/<ticket_number>/messages")
def get_messages(ticket_number):
    """Read the private thread of one ticket (student + staff only).

    The conversation is addressed by its ticket number: only the student
    who holds the ticket (same link he uses to follow his queue position)
    and the staff panel can reach it — there is no listing, search or
    cross-ticket access.
    """
    ticket, err = _chat_ticket_or_404(ticket_number)
    if err:
        return err
    return jsonify(
        {
            "ticket": {
                "ticket_number": ticket["ticket_number"],
                "status": ticket["status"],
                "service_name": ticket["service_name"],
                "customer_name": ticket["customer_name"],
                "request_text": ticket["request_text"],
                "people_ahead": ticket["people_ahead"],
            },
            "can_student_send": ticket["chat_can_student_send"],
            "can_staff_send": ticket["chat_can_staff_send"],
            "messages": models.list_messages(ticket["id"]),
        }
    )


@api_bp.post("/tickets/<ticket_number>/messages")
def post_message(ticket_number):
    """Send one chat message (text and/or file/image attachment).

    Body: JSON {"sender": "student|staff", "text": "..."} or multipart
    form-data with the same fields plus ``file``.

    Rules (enforced server-side, mirrored in the UI):
    * student -> 403 ``not_your_turn`` until the ticket is SERVING;
    * staff   -> allowed while WAITING or SERVING;
    * DONE/CANCELLED -> 403 ``closed`` for both sides.
    """
    ticket, err = _chat_ticket_or_404(ticket_number)
    if err:
        return err

    if request.is_json:
        payload = request.get_json(silent=True) or {}
        upload = None
    else:
        payload = request.form.to_dict()
        upload = request.files.get("file")

    sender = (payload.get("sender") or "").strip().lower()
    text = payload.get("text") or ""
    if sender not in ("student", "staff"):
        return _error("'sender' must be 'student' or 'staff'", 400)

    # reject locked senders BEFORE any file is written to disk: a student
    # who is not yet at his turn must not leave orphan attachments behind.
    allowed = (
        ticket["chat_can_staff_send"]
        if sender == "staff"
        else ticket["chat_can_student_send"]
    )
    if not allowed:
        reason = "closed" if ticket["status"] in ("DONE", "CANCELLED") else "not_your_turn"
        return (
            jsonify(
                {
                    "error": (
                        "this conversation is closed"
                        if reason == "closed"
                        else "messaging unlocks when your turn arrives "
                        "(the ticket is being served)"
                    ),
                    "reason": reason,
                    "status": ticket["status"],
                }
            ),
            403,
        )

    file_info = None
    if upload is not None and upload.filename:
        try:
            file_info = _save_attachment(ticket, upload)
        except ValueError as exc:
            return _error(str(exc), 400)

    try:
        message = models.add_message(
            ticket["id"], sender.upper(), text, file_info
        )
    except models.ChatLocked as exc:
        reason = "closed" if "closed" in str(exc) else "not_your_turn"
        return (
            jsonify(
                {
                    "error": str(exc),
                    "reason": reason,
                    "status": ticket["status"],
                }
            ),
            403,
        )
    except ValueError as exc:
        return _error(str(exc), 400)

    return (
        jsonify(
            {
                "message": message,
                "can_student_send": ticket["status"] == "SERVING",
                "can_staff_send": ticket["status"] in ("WAITING", "SERVING"),
            }
        ),
        201,
    )


# --------------------------------------------------------------- demo utils


@api_bp.post("/demo/reset")
def demo_reset():
    """Reset the database to a clean state (live-demo convenience).

    Intended for the demonstration environment only; remove or protect
    this route before any real deployment.
    """
    models.reset_all()
    return jsonify({"reset": True, "stats": models.global_stats()})


@api_bp.get("/load-levels")
def load_levels():
    """Expose the three load levels and current thresholds."""
    from flask import current_app

    return jsonify(
        {
            "levels": list(LEVELS),
            "busy_threshold": current_app.config["BUSY_THRESHOLD"],
            "high_threshold": current_app.config["HIGH_THRESHOLD"],
            "rule": "NORMAL < busy_threshold <= BUSY < high_threshold <= HIGH LOAD",
        }
    )
