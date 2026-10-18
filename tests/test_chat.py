"""Tests for the private chat feature (student <-> staff) and the
ticket request/inquiry field.

Covers the rules required by the product decision:

* issuing a ticket carries the customer's request/inquiry text;
* the conversation is per-ticket (no cross-ticket access, no listing);
* the STUDENT cannot send ANY message, image or file until his turn
  arrives (ticket status SERVING) - the API rejects with 403
  ``not_your_turn``;
* the staff can message while the ticket is WAITING or SERVING;
* once the ticket is DONE or CANCELLED the conversation is closed for
  both sides;
* attachments are stored, size-capped and served per-ticket.
"""

import io
import os

from app import models

SERVICE = "it_support"


_STUDENT_SEQ = [0]


def _create(client, name="Sara", request_text="", service=SERVICE):
    _STUDENT_SEQ[0] += 1
    res = client.post(
        "/api/tickets",
        json={
            "service_code": service,
            "customer_name": name,
            "student_id": f"44100{_STUDENT_SEQ[0]:04d}",
            "request_text": request_text,
        },
    )
    assert res.status_code == 201, (res.status_code, res.get_json())
    return res.get_json()["ticket"]


def _send(client, number, sender, text="hello", file=None, filename="a.png",
          data=b"png-bytes", expect=201):
    if file is None and text is not None:
        res = client.post(
            f"/api/tickets/{number}/messages",
            json={"sender": sender, "text": text},
        )
    else:
        res = client.post(
            f"/api/tickets/{number}/messages",
            data={
                "sender": sender,
                "text": text or "",
                "file": (io.BytesIO(data), filename),
            },
            content_type="multipart/form-data",
        )
    assert res.status_code == expect, (res.status_code, res.get_json())
    return res.get_json()


def _serve(client, number):
    res = client.post(f"/api/services/{SERVICE}/next")
    assert res.status_code == 200


# ------------------------------------------------------------ request field


def test_request_text_stored_and_returned(client):
    ticket = _create(client, request_text="حسابي الجامعي معطل ولا أستطيع الدخول")
    assert ticket["request_text"] == "حسابي الجامعي معطل ولا أستطيع الدخول"

    fetched = client.get(f"/api/tickets/{ticket['ticket_number']}").get_json()
    assert fetched["ticket"]["request_text"] == ticket["request_text"]

    listing = client.get("/api/tickets?service_code=it_support").get_json()
    assert listing["tickets"][0]["request_text"] == ticket["request_text"]

    # shown to the student on his ticket page and to staff on /admin,
    # never on the public queue board
    page = client.get(f"/ticket/{ticket['ticket_number']}")
    assert page.status_code == 200
    assert "حسابي الجامعي معطل".encode("utf-8") in page.data
    admin = client.get("/admin")
    assert "حسابي الجامعي معطل".encode("utf-8") in admin.data
    board = client.get("/queue")
    assert "حسابي الجامعي معطل".encode("utf-8") not in board.data


def test_request_text_optional_and_capped(client):
    ticket = _create(client)  # no request text at all
    assert ticket["request_text"] == ""

    long = "أ" * 900
    ticket = _create(client, request_text=long, name="Omar")
    assert len(ticket["request_text"]) == models.MAX_REQUEST_TEXT


# ------------------------------------------------------------ chat locking


def test_student_cannot_send_until_his_turn(client):
    ticket = _create(client, request_text="أحتاج إعادة تعيين كلمة المرور")

    # WAITING: the student is locked out of sending ANYTHING
    res = _send(client, ticket["ticket_number"], "student", expect=403)
    assert res["reason"] == "not_your_turn"

    res = _send(client, ticket["ticket_number"], "student", text=None,
                file=True, filename="photo.png", expect=403)
    assert res["reason"] == "not_your_turn"

    # staff may open the conversation while the customer is still waiting
    _send(client, ticket["ticket_number"], "staff", text="أهلاً، سنخدمك حال وصول دورك")

    # turn arrives -> student can send
    _serve(client, ticket["ticket_number"])
    _send(client, ticket["ticket_number"], "student", text="شكرًا، أنا حاضر")

    thread = client.get(f"/api/tickets/{ticket['ticket_number']}/messages")
    body = thread.get_json()
    assert [m["sender"] for m in body["messages"]] == ["STAFF", "STUDENT"]
    assert body["can_student_send"] is True


def test_chat_closed_after_done(client):
    ticket = _create(client)
    _serve(client, ticket["ticket_number"])
    _send(client, ticket["ticket_number"], "student", text="سؤال سريع")

    res = client.post(
        f"/api/tickets/{ticket['ticket_number']}/status",
        json={"status": "DONE"},
    )
    assert res.status_code == 200

    res = _send(client, ticket["ticket_number"], "student", expect=403)
    assert res["reason"] == "closed"
    res = _send(client, ticket["ticket_number"], "staff", expect=403)
    assert res["reason"] == "closed"

    # the thread stays readable for both sides (history)
    body = client.get(f"/api/tickets/{ticket['ticket_number']}/messages").get_json()
    assert len(body["messages"]) == 1


def test_chat_closed_after_cancel(client):
    ticket = _create(client)
    res = client.post(f"/api/tickets/{ticket['ticket_number']}/cancel")
    assert res.status_code == 200
    res = _send(client, ticket["ticket_number"], "staff", expect=403)
    assert res["reason"] == "closed"


def test_staff_cannot_message_finished_ticket(client):
    ticket = _create(client)
    _serve(client, ticket["ticket_number"])
    client.post(
        f"/api/tickets/{ticket['ticket_number']}/status", json={"status": "DONE"}
    )
    res = _send(client, ticket["ticket_number"], "staff", expect=403)
    assert res["reason"] == "closed"


def test_message_validation(client):
    ticket = _create(client)
    # invalid sender
    res = client.post(
        f"/api/tickets/{ticket['ticket_number']}/messages",
        json={"sender": "admin", "text": "hi"},
    )
    assert res.status_code == 400
    # empty message
    res = client.post(
        f"/api/tickets/{ticket['ticket_number']}/messages",
        json={"sender": "staff", "text": "   "},
    )
    assert res.status_code == 400
    # unknown ticket
    res = client.post("/api/tickets/ZZ-999/messages", json={"sender": "staff"})
    assert res.status_code == 404
    res = client.get("/api/tickets/ZZ-999/messages")
    assert res.status_code == 404


# ------------------------------------------------------------ privacy


def test_thread_is_private_per_ticket(client):
    a = _create(client, name="Sara", request_text="طلب سارة")
    b = _create(client, name="Noura", request_text="طلب نورة")

    _serve(client, a["ticket_number"])
    _send(client, a["ticket_number"], "student", text="رسالة سرية لسارة")

    # Sara's message must not leak into Noura's thread
    body = client.get(f"/api/tickets/{b['ticket_number']}/messages").get_json()
    assert body["messages"] == []
    assert "رسالة سرية".encode("utf-8") not in client.get(
        f"/api/tickets/{b['ticket_number']}/messages"
    ).data
    # and not into any public page
    for path in ("/", "/queue", "/admin"):
        assert "رسالة سرية".encode("utf-8") not in client.get(path).data


def test_chat_page_reachable_only_with_ticket_number(client):
    ticket = _create(client, request_text="استفسار عن الشهادة")
    ok = client.get(f"/chat/{ticket['ticket_number']}")
    assert ok.status_code == 200
    assert b"chatPage" in ok.data
    staff_view = client.get(f"/chat/{ticket['ticket_number']}?staff=1")
    assert staff_view.status_code == 200
    assert b'data-role-mode="staff"' in staff_view.data
    assert b'data-role-mode="student"' in ok.data
    missing = client.get("/chat/ZZ-999")
    assert missing.status_code == 404


# ------------------------------------------------------------ attachments


def test_attachment_upload_and_serving(client):
    ticket = _create(client)
    _serve(client, ticket["ticket_number"])

    payload = _send(
        client, ticket["ticket_number"], "student", text=None,
        file=True, filename="screenshot.png", data=b"\x89PNG-fake-image",
    )
    msg = payload["message"]
    assert msg["file_name"] == "screenshot.png"
    assert msg["file_size"] == len(b"\x89PNG-fake-image")

    stored = msg["stored_name"]
    assert stored and stored != "screenshot.png"  # random prefix
    folder = os.path.join(client.application.config["UPLOAD_DIR"],
                          ticket["ticket_number"])
    assert os.path.exists(os.path.join(folder, stored))

    # served inline for images, per ticket
    url = f"/uploads/{ticket['ticket_number']}/{stored}"
    res = client.get(url)
    assert res.status_code == 200
    assert res.data == b"\x89PNG-fake-image"

    # another ticket cannot fetch it by path (unknown folder -> 404)
    res = client.get(f"/uploads/AA-001/{stored}")
    assert res.status_code == 404

    # path traversal is refused
    res = client.get(f"/uploads/{ticket['ticket_number']}/..%2f..%2fapp.py")
    assert res.status_code in (404, 400)


def test_attachment_size_cap(client):
    ticket = _create(client)
    _serve(client, ticket["ticket_number"])
    big = b"x" * (client.application.config["MAX_UPLOAD_MB"] * 1024 * 1024 + 5)
    res = _send(
        client, ticket["ticket_number"], "student", text=None,
        file=True, filename="big.bin", data=big, expect=400,
    )
    assert "large" in res["error"]


def test_messages_count_on_ticket(client):
    ticket = _create(client)
    assert ticket["messages_count"] == 0
    _send(client, ticket["ticket_number"], "staff", text="welcome")
    fetched = client.get(f"/api/tickets/{ticket['ticket_number']}").get_json()
    assert fetched["ticket"]["messages_count"] == 1
