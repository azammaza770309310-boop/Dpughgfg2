"""End-to-end API tests using the Flask test client.

These mirror the manual QA checklist required before delivery:
ticket creation, queue listing, serving/completing, load transitions
and the demo reset endpoint.
"""

SERVICE = "it_support"


def create(client, service=SERVICE, name="Ali", code=201):
    res = client.post(
        "/api/tickets",
        json={"service_code": service, "customer_name": name},
    )
    assert res.status_code == code
    return res.get_json()


def test_services_endpoint(client):
    res = client.get("/api/services")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["services"]) == 4
    assert data["stats"]["overall_load"] == "NORMAL"


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"


def test_html_pages_render(client):
    # Arabic is the primary UI language (English is secondary, via JS toggle).
    for path in ("/", "/queue", "/admin"):
        res = client.get(path)
        assert res.status_code == 200
        assert "كراود كلاود".encode("utf-8") in res.data
        assert b'dir="rtl"' in res.data


def test_create_ticket_flow(client):
    data = create(client, name="Abdulaziz")
    ticket = data["ticket"]
    assert ticket["ticket_number"] == "IT-001"
    assert ticket["status"] == "WAITING"
    assert ticket["people_ahead"] == 0

    page = client.get(f"/ticket/{ticket['ticket_number']}")
    assert page.status_code == 200

    missing = client.get("/ticket/ZZ-999")
    assert missing.status_code == 404


def test_create_ticket_validation(client):
    res = client.post("/api/tickets", json={"service_code": "nope"})
    assert res.status_code == 404
    res = client.post("/api/tickets", json={})
    assert res.status_code == 400
    res = client.post("/api/tickets", json={"service_id": 99})
    assert res.status_code == 404


def test_list_tickets_filter(client):
    create(client, name="A")
    create(client, name="B")
    res = client.get(f"/api/tickets?service_code={SERVICE}&status=WAITING")
    assert res.status_code == 200
    body = res.get_json()
    assert body["count"] == 2
    assert all(t["status"] == "WAITING" for t in body["tickets"])


def test_load_escalation_normal_busy_high(client):
    """3 -> BUSY at ticket 3, HIGH LOAD at ticket 6 (test thresholds)."""
    for i in range(6):
        create(client, name=f"user-{i+1}")
    res = client.get("/api/services")
    svc = next(
        s for s in res.get_json()["services"] if s["code"] == SERVICE
    )
    assert svc["waiting"] == 6
    assert svc["load"] == "HIGH LOAD"
    assert res.get_json()["stats"]["overall_load"] == "HIGH LOAD"


def test_load_de_escalation_by_serving(client):
    for _ in range(6):
        create(client)

    def service_state():
        res = client.get("/api/services")
        return next(
            s for s in res.get_json()["services"] if s["code"] == SERVICE
        )

    # HIGH LOAD (6 waiting) -> serve 1 -> 5 waiting -> BUSY
    client.post(f"/api/services/{SERVICE}/next")
    assert service_state()["load"] == "BUSY"
    # complete the serving ticket, call one more -> 4 waiting -> still BUSY
    ticket = client.get(f"/api/tickets?service_code={SERVICE}&status=SERVING").get_json()["tickets"][0]
    client.post(f"/api/tickets/{ticket['ticket_number']}/status", json={"status": "DONE"})
    client.post(f"/api/services/{SERVICE}/next")
    assert service_state()["load"] == "BUSY"
    # serve 2 more -> 2 waiting -> NORMAL
    client.post(f"/api/services/{SERVICE}/next")
    ticket = client.get(f"/api/tickets?service_code={SERVICE}&status=SERVING").get_json()["tickets"][0]
    client.post(f"/api/tickets/{ticket['ticket_number']}/status", json={"status": "DONE"})
    client.post(f"/api/services/{SERVICE}/next")
    ticket = client.get(f"/api/tickets?service_code={SERVICE}&status=SERVING").get_json()["tickets"][0]
    client.post(f"/api/tickets/{ticket['ticket_number']}/status", json={"status": "DONE"})
    assert service_state()["load"] == "NORMAL"


def test_status_transition_validation(client):
    data = create(client)
    number = data["ticket"]["ticket_number"]
    res = client.post(f"/api/tickets/{number}/status", json={"status": "DONE"})
    assert res.status_code == 409
    res = client.post(f"/api/tickets/{number}/status", json={"status": "BANANA"})
    assert res.status_code == 400


def test_customer_cancel(client):
    data = create(client)
    number = data["ticket"]["ticket_number"]
    res = client.post(f"/api/tickets/{number}/cancel")
    assert res.status_code == 200
    assert res.get_json()["ticket"]["status"] == "CANCELLED"
    # cancelling twice is rejected (already CANCELLED)
    res = client.post(f"/api/tickets/{number}/cancel")
    assert res.status_code == 409


def test_demo_reset(client):
    create(client)
    create(client)
    res = client.post("/api/demo/reset")
    assert res.status_code == 200
    stats = client.get("/api/stats").get_json()
    assert stats["waiting"] == 0
    assert stats["total"] == 0
    assert stats["overall_load"] == "NORMAL"
    # numbering restarts after reset
    data = create(client)
    assert data["ticket"]["ticket_number"] == "IT-001"


def test_load_levels_endpoint(client):
    res = client.get("/api/load-levels")
    assert res.status_code == 200
    data = res.get_json()
    assert data["levels"] == ["NORMAL", "BUSY", "HIGH LOAD"]
    assert data["busy_threshold"] == 3
    assert data["high_threshold"] == 6


def test_create_ticket_with_student_id(client):
    """Student ID is stored and echoed back on ticket + pages."""
    res = client.post(
        "/api/tickets",
        json={"service_code": SERVICE, "customer_name": "Nora", "student_id": "441002357"},
    )
    assert res.status_code == 201
    ticket = res.get_json()["ticket"]
    assert ticket["student_id"] == "441002357"
    assert ticket["ticket_number"] == "IT-001"

    # ticket page shows the student ID
    page = client.get(f"/ticket/{ticket['ticket_number']}")
    assert page.status_code == 200
    assert b"441002357" in page.data

    # admin + queue pages expose it too (server-rendered first paint)
    for path in ("/admin", "/queue"):
        page = client.get(path)
        assert page.status_code == 200
        assert b"441002357" in page.data


def test_duplicate_active_student_id_rejected(client):
    """One student cannot hold two active tickets for the same service."""
    first = client.post(
        "/api/tickets",
        json={"service_code": SERVICE, "customer_name": "Sara", "student_id": "441999888"},
    )
    assert first.status_code == 201

    dup = client.post(
        "/api/tickets",
        json={"service_code": SERVICE, "customer_name": "Sara", "student_id": "441999888"},
    )
    assert dup.status_code == 409
    body = dup.get_json()
    assert body["ticket"] == first.get_json()["ticket"]["ticket_number"]

    # same student ID is fine on a DIFFERENT service
    other = client.post(
        "/api/tickets",
        json={"service_code": "registration_support", "customer_name": "Sara", "student_id": "441999888"},
    )
    assert other.status_code == 201

    # after the first ticket is done, the student can take a new ticket
    number = first.get_json()["ticket"]["ticket_number"]
    client.post(f"/api/tickets/{number}/status", json={"status": "SERVING"})
    client.post(f"/api/tickets/{number}/status", json={"status": "DONE"})
    again = client.post(
        "/api/tickets",
        json={"service_code": SERVICE, "customer_name": "Sara", "student_id": "441999888"},
    )
    assert again.status_code == 201
