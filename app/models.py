"""Data-access layer: services, tickets, queue operations and statistics.

All queue mutations are written so that they stay correct when several
workers/requests run at the same time:

* ``create_ticket``  - one transaction (counter + insert).
* ``call_next``      - atomic claim via a guarded UPDATE (a ticket can
  only move WAITING -> SERVING once, even if two staff members click
  at the same moment).
* ``update_status``  - guarded UPDATE per allowed transition.
"""

import sqlite3

from flask import current_app

from .db import get_conn
from .load_status import compute_load, highest_level, load_percent

TICKET_STATUSES = ("WAITING", "SERVING", "DONE", "CANCELLED")

MAX_REQUEST_TEXT = 500
MAX_MESSAGE_TEXT = 2000


class ChatLocked(ValueError):
    """Raised when a chat message is not allowed for the ticket state.

    The conversation is strictly personal (student <-> staff of that
    ticket) and the STUDENT side stays read-only until his turn actually
    arrives (ticket is being served). Staff may message while the ticket
    is WAITING or SERVING; nobody can write to a finished/cancelled
    ticket.
    """


class DuplicateActiveTicket(ValueError):
    """Raised when a student ID already holds an active ticket for a service.

    Raised inside the creation transaction so the check is atomic under
    concurrent workers: BEGIN IMMEDIATE serialises writers, so two requests
    with the same student ID cannot both pass the guard.
    """


VALID_TRANSITIONS = {
    ("WAITING", "SERVING"),
    ("WAITING", "CANCELLED"),
    ("SERVING", "DONE"),
    ("SERVING", "CANCELLED"),
}

# ------------------------------------------------------------------ services


def _service_stats_sql(where: str = ""):
    return f"""
        SELECT s.id, s.code, s.prefix, s.name, s.description,
               COALESCE(c.last_number, 0) AS last_number,
               (SELECT COUNT(*) FROM tickets t
                 WHERE t.service_id = s.id AND t.status = 'WAITING') AS waiting,
               (SELECT COUNT(*) FROM tickets t
                 WHERE t.service_id = s.id AND t.status = 'SERVING') AS serving,
               (SELECT COUNT(*) FROM tickets t
                 WHERE t.service_id = s.id AND t.status = 'DONE'
                   AND date(t.finished_at) = date('now')) AS done_today,
               (SELECT COUNT(*) FROM tickets t
                 WHERE t.service_id = s.id) AS total
        FROM services s
        LEFT JOIN service_counters c ON c.service_id = s.id
        {where}
        ORDER BY s.id
    """


def _serialize_service(row) -> dict:
    cfg = current_app.config
    waiting = row["waiting"]
    return {
        "id": row["id"],
        "code": row["code"],
        "prefix": row["prefix"],
        "name": row["name"],
        "description": row["description"],
        "waiting": waiting,
        "serving": row["serving"],
        "done_today": row["done_today"],
        "total": row["total"],
        "last_number": row["last_number"],
        "load": compute_load(waiting, cfg["BUSY_THRESHOLD"], cfg["HIGH_THRESHOLD"]),
        "load_percent": load_percent(waiting, cfg["HIGH_THRESHOLD"]),
        "busy_threshold": cfg["BUSY_THRESHOLD"],
        "high_threshold": cfg["HIGH_THRESHOLD"],
    }


def list_services() -> list:
    rows = get_conn().execute(_service_stats_sql()).fetchall()
    return [_serialize_service(r) for r in rows]


def get_service(identifier):
    """Fetch one service (with live stats) by numeric id or code."""
    conn = get_conn()
    if isinstance(identifier, int) or str(identifier).isdigit():
        where, arg = "WHERE s.id = ?", int(identifier)
    else:
        where, arg = "WHERE s.code = ?", str(identifier)
    row = conn.execute(_service_stats_sql(where), (arg,)).fetchone()
    return _serialize_service(row) if row else None


# ------------------------------------------------------------------- tickets


def create_ticket(service_id: int, customer_name: str = "", student_id: str = "",
                  request_text: str = ""):
    """Issue the next ticket for a service (atomic counter + insert).

    ``student_id`` is optional at the API level (load tests and scripts use
    the bare form); when provided, an active (WAITING/SERVING) ticket for the
    same service and student raises DuplicateActiveTicket so one student
    cannot hold two live tickets for the same counter.

    ``request_text`` stores what the customer wants (his request or
    inquiry) so the staff sees it before serving.
    """
    student_id = (student_id or "").strip()
    request_text = (request_text or "").strip()[:MAX_REQUEST_TEXT]
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        svc = conn.execute(
            "SELECT id, prefix FROM services WHERE id = ?", (service_id,)
        ).fetchone()
        if svc is None:
            conn.execute("ROLLBACK")
            return None
        if student_id:
            dup = conn.execute(
                "SELECT ticket_number FROM tickets "
                "WHERE service_id = ? AND student_id = ? "
                "AND status IN ('WAITING', 'SERVING') LIMIT 1",
                (service_id, student_id),
            ).fetchone()
            if dup is not None:
                conn.execute("ROLLBACK")
                raise DuplicateActiveTicket(dup["ticket_number"])
        counter = conn.execute(
            "SELECT last_number FROM service_counters WHERE service_id = ?",
            (service_id,),
        ).fetchone()
        next_number = (counter["last_number"] if counter else 0) + 1
        ticket_number = f"{svc['prefix']}-{next_number:03d}"
        conn.execute(
            "UPDATE service_counters SET last_number = ? WHERE service_id = ?",
            (next_number, service_id),
        )
        conn.execute(
            "INSERT INTO tickets (ticket_number, service_id, customer_name, student_id, request_text) "
            "VALUES (?, ?, ?, ?, ?)",
            (ticket_number, service_id, (customer_name or "").strip(), student_id, request_text),
        )
        conn.execute("COMMIT")
    except sqlite3.Error:
        conn.execute("ROLLBACK")
        raise
    return get_ticket(ticket_number)


def get_ticket(ticket_number: str):
    """Fetch a ticket by number, with live queue position and service load."""
    conn = get_conn()
    row = conn.execute(
        """
        SELECT t.id, t.ticket_number, t.service_id, t.customer_name, t.student_id,
               t.request_text, t.status,
               t.created_at, t.called_at, t.finished_at,
               s.code AS service_code, s.name AS service_name, s.prefix
        FROM tickets t JOIN services s ON s.id = t.service_id
        WHERE UPPER(t.ticket_number) = UPPER(?)
        """,
        (str(ticket_number),),
    ).fetchone()
    if row is None:
        return None

    ticket = dict(row)
    cfg = current_app.config
    if ticket["status"] == "WAITING":
        ahead = conn.execute(
            "SELECT COUNT(*) AS c FROM tickets "
            "WHERE service_id = ? AND status = 'WAITING' AND id < ?",
            (ticket["service_id"], ticket["id"]),
        ).fetchone()["c"]
        ticket["people_ahead"] = ahead
        ticket["estimated_wait_minutes"] = ahead * cfg["AVG_SERVICE_MINUTES"]
    else:
        ticket["people_ahead"] = 0
        ticket["estimated_wait_minutes"] = 0

    waiting = conn.execute(
        "SELECT COUNT(*) AS c FROM tickets WHERE service_id = ? AND status = 'WAITING'",
        (ticket["service_id"],),
    ).fetchone()["c"]
    ticket["queue_length"] = waiting
    ticket["load"] = compute_load(waiting, cfg["BUSY_THRESHOLD"], cfg["HIGH_THRESHOLD"])
    ticket["load_percent"] = load_percent(waiting, cfg["HIGH_THRESHOLD"])
    ticket["chat_can_student_send"] = ticket["status"] == "SERVING"
    ticket["chat_can_staff_send"] = ticket["status"] in ("WAITING", "SERVING")
    ticket["messages_count"] = conn.execute(
        "SELECT COUNT(*) AS c FROM ticket_messages WHERE ticket_id = ?",
        (ticket["id"],),
    ).fetchone()["c"]
    return ticket


def list_tickets(service_id=None, status=None, limit: int = 50, waiting_first=False):
    """List tickets, newest first by default (queue board reorders in SQL)."""
    conn = get_conn()
    clauses, args = [], []
    if service_id is not None:
        clauses.append("t.service_id = ?")
        args.append(service_id)
    if status:
        clauses.append("t.status = ?")
        args.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    order = (
        "ORDER BY CASE t.status WHEN 'SERVING' THEN 0 WHEN 'WAITING' THEN 1 "
        "ELSE 2 END, t.id ASC"
        if waiting_first
        else "ORDER BY t.id DESC"
    )
    args.append(int(limit))
    rows = conn.execute(
        f"""
        SELECT t.id, t.ticket_number, t.service_id, t.customer_name, t.student_id,
               t.request_text, t.status,
               t.created_at, t.called_at, t.finished_at,
               s.code AS service_code, s.name AS service_name, s.prefix
        FROM tickets t JOIN services s ON s.id = t.service_id
        {where}
        {order}
        LIMIT ?
        """,
        args,
    ).fetchall()
    return [dict(r) for r in rows]


def call_next(service_id: int):
    """Move the oldest WAITING ticket to SERVING (atomic claim)."""
    conn = get_conn()
    for _ in range(5):  # retry if another clerk claimed the same ticket
        row = conn.execute(
            "SELECT id, ticket_number FROM tickets "
            "WHERE service_id = ? AND status = 'WAITING' "
            "ORDER BY id ASC LIMIT 1",
            (service_id,),
        ).fetchone()
        if row is None:
            return None
        cur = conn.execute(
            "UPDATE tickets SET status = 'SERVING', called_at = datetime('now') "
            "WHERE id = ? AND status = 'WAITING'",
            (row["id"],),
        )
        if cur.rowcount == 1:
            return get_ticket(row["ticket_number"])
    return None


def update_ticket_status(ticket_number: str, new_status: str):
    """Apply a guarded status transition and return the updated ticket."""
    if new_status not in TICKET_STATUSES:
        raise ValueError(f"invalid status: {new_status}")

    ticket = get_ticket(ticket_number)
    if ticket is None:
        return None
    current = ticket["status"]
    if (current, new_status) not in VALID_TRANSITIONS:
        raise ValueError(
            f"transition {current} -> {new_status} is not allowed"
        )

    conn = get_conn()
    sets = ["status = ?"]
    args = [new_status]
    if new_status == "SERVING":
        sets.append("called_at = datetime('now')")
    if new_status in ("DONE", "CANCELLED"):
        sets.append("finished_at = datetime('now')")
    args.extend([ticket["id"], current])

    cur = conn.execute(
        f"UPDATE tickets SET {', '.join(sets)} WHERE id = ? AND status = ?",
        args,
    )
    if cur.rowcount != 1:
        # Someone else changed the ticket meanwhile.
        return get_ticket(ticket_number)
    return get_ticket(ticket_number)


def cancel_ticket(ticket_number: str):
    """Customer-side cancellation (only possible while WAITING)."""
    return update_ticket_status(ticket_number, "CANCELLED")


def reset_all():
    """Demo utility: clear every ticket and restart numbering."""
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM ticket_messages")
        conn.execute("DELETE FROM tickets")
        conn.execute("UPDATE service_counters SET last_number = 0")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('tickets', 'ticket_messages')"
        )
        conn.execute("COMMIT")
    except sqlite3.Error:
        conn.execute("ROLLBACK")
        raise
    return True


# ------------------------------------------------------------------ chat


def list_messages(ticket_id: int) -> list:
    """All chat messages of one ticket, oldest first (thread order)."""
    rows = get_conn().execute(
        """
        SELECT id, sender, text, file_name, stored_name, file_mime, file_size, created_at
          FROM ticket_messages
         WHERE ticket_id = ?
         ORDER BY id ASC
        """,
        (ticket_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_message(ticket_id: int, sender: str, text: str = "",
                 file_info: dict | None = None) -> dict:
    """Append one chat message, enforcing the private-chat rules.

    Rules (authoritative here, mirrored in the UI):
    * STUDENT may write ONLY while his turn is being served (SERVING)
      - i.e. he can read the thread from the moment the ticket is issued
      but cannot send any message/file until his turn arrives.
    * STAFF may write while the ticket is WAITING or SERVING.
    * Nobody can write once the ticket is DONE or CANCELLED.
    """
    sender = (sender or "").strip().upper()
    if sender not in ("STUDENT", "STAFF"):
        raise ValueError("sender must be STUDENT or STAFF")

    status_row = get_conn().execute(
        "SELECT status FROM tickets WHERE id = ?", (ticket_id,)
    ).fetchone()
    if status_row is None:
        return None
    status = status_row["status"]

    if status == "DONE" or status == "CANCELLED":
        raise ChatLocked("this conversation is closed")
    if sender == "STUDENT" and status != "SERVING":
        raise ChatLocked(
            "messaging unlocks when your turn arrives (the ticket is being served)"
        )

    text = (text or "").strip()[:MAX_MESSAGE_TEXT]
    f = file_info or {}
    if not text and not f.get("stored_name"):
        raise ValueError("a message needs text or an attached file")

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO ticket_messages (ticket_id, sender, text,
                                     file_name, stored_name, file_mime, file_size)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticket_id,
            sender,
            text,
            (f.get("file_name") or "")[:200],
            f.get("stored_name") or "",
            (f.get("file_mime") or "")[:100],
            int(f.get("file_size") or 0),
        ),
    )
    row = conn.execute(
        "SELECT id, sender, text, file_name, stored_name, file_mime, file_size, created_at "
        "FROM ticket_messages WHERE ticket_id = ? ORDER BY id DESC LIMIT 1",
        (ticket_id,),
    ).fetchone()
    return dict(row)


def count_tickets() -> int:
    return get_conn().execute("SELECT COUNT(*) AS c FROM tickets").fetchone()["c"]


# ------------------------------------------------------------------ simulator


def auto_serve_tick():
    """One step of the optional service simulator.

    For every service, finish the ticket currently being served (if any)
    and then call the next waiting ticket. It gives the live demo a
    moving queue without requiring manual staff clicks.
    """
    conn = get_conn()
    for svc in list_services():
        conn.execute(
            """
            UPDATE tickets
               SET status = 'DONE', finished_at = datetime('now')
             WHERE id = (
                   SELECT id FROM tickets
                    WHERE service_id = ? AND status = 'SERVING'
                    ORDER BY id ASC LIMIT 1)
               AND status = 'SERVING'
            """,
            (svc["id"],),
        )
        call_next(svc["id"])


# ------------------------------------------------------------------ overview


def global_stats() -> dict:
    """Cross-service overview used by the dashboard header."""
    conn = get_conn()
    services = list_services()
    row = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM tickets WHERE status = 'WAITING')  AS waiting,
            (SELECT COUNT(*) FROM tickets WHERE status = 'SERVING')  AS serving,
            (SELECT COUNT(*) FROM tickets
              WHERE status = 'DONE'
                AND date(finished_at) = date('now'))                AS done_today,
            (SELECT COUNT(*) FROM tickets)                            AS total,
            (SELECT COUNT(*) FROM tickets
              WHERE date(created_at) = date('now'))                   AS created_today
        """
    ).fetchone()
    overall = highest_level(s["load"] for s in services)
    return {
        "waiting": row["waiting"],
        "serving": row["serving"],
        "done_today": row["done_today"],
        "created_today": row["created_today"],
        "total": row["total"],
        "overall_load": overall,
        "services_count": len(services),
        "busy_threshold": current_app.config["BUSY_THRESHOLD"],
        "high_threshold": current_app.config["HIGH_THRESHOLD"],
    }
