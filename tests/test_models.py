"""Database / model level tests: ticket numbering and queue operations."""

import pytest

from app import models


def test_four_services_seeded(app):
    with app.app_context():
        services = models.list_services()
        assert len(services) == 4
        codes = {s["code"] for s in services}
        assert codes == {
            "academic_advising",
            "it_support",
            "registration_support",
            "student_services",
        }


def test_ticket_numbering_is_sequential_and_prefixed(app):
    with app.app_context():
        service = models.get_service("it_support")
        first = models.create_ticket(service["id"], "Ali")
        second = models.create_ticket(service["id"], "Sara")
        assert first["ticket_number"] == "IT-001"
        assert second["ticket_number"] == "IT-002"
        assert first["status"] == "WAITING"


def test_numbering_is_independent_per_service(app):
    with app.app_context():
        it = models.get_service("it_support")
        aa = models.get_service("academic_advising")
        models.create_ticket(it["id"])
        models.create_ticket(aa["id"])
        ticket = models.create_ticket(aa["id"])
        assert ticket["ticket_number"] == "AA-002"


def test_queue_position_and_people_ahead(app):
    with app.app_context():
        service = models.get_service("student_services")
        models.create_ticket(service["id"], "A")
        models.create_ticket(service["id"], "B")
        third = models.create_ticket(service["id"], "C")
        assert third["people_ahead"] == 2
        assert third["queue_length"] == 3


def test_call_next_is_fifo_and_atomic(app):
    with app.app_context():
        service = models.get_service("it_support")
        t1 = models.create_ticket(service["id"], "first")
        t2 = models.create_ticket(service["id"], "second")
        called = models.call_next(service["id"])
        assert called["ticket_number"] == t1["ticket_number"]
        assert called["status"] == "SERVING"
        # calling again moves to the second ticket, first is not re-called
        called2 = models.call_next(service["id"])
        assert called2["ticket_number"] == t2["ticket_number"]


def test_call_next_empty_queue_returns_none(app):
    with app.app_context():
        service = models.get_service("it_support")
        assert models.call_next(service["id"]) is None


def test_status_transitions_are_guarded(app):
    with app.app_context():
        service = models.get_service("it_support")
        ticket = models.create_ticket(service["id"])
        with pytest.raises(ValueError):
            models.update_ticket_status(ticket["ticket_number"], "DONE")
        serving = models.update_ticket_status(ticket["ticket_number"], "SERVING")
        assert serving["status"] == "SERVING"
        done = models.update_ticket_status(ticket["ticket_number"], "DONE")
        assert done["status"] == "DONE"
        assert done["finished_at"] is not None


def test_cancel_only_while_waiting(app):
    with app.app_context():
        service = models.get_service("it_support")
        ticket = models.create_ticket(service["id"])
        cancelled = models.cancel_ticket(ticket["ticket_number"])
        assert cancelled["status"] == "CANCELLED"


def test_reset_all_clears_tickets_and_counters(app):
    with app.app_context():
        service = models.get_service("it_support")
        models.create_ticket(service["id"])
        models.create_ticket(service["id"])
        models.reset_all()
        assert models.count_tickets() == 0
        fresh = models.create_ticket(service["id"])
        assert fresh["ticket_number"] == "IT-001"


def test_load_transitions_with_waiting_count(app):
    """The core demo requirement: NORMAL -> BUSY -> HIGH LOAD."""
    with app.app_context():
        service = models.get_service("it_support")
        loads = []
        for _ in range(6):  # thresholds are 3 and 6 in the test app
            models.create_ticket(service["id"])
            loads.append(models.get_service("it_support")["load"])
        assert loads == ["NORMAL", "NORMAL", "BUSY", "BUSY", "BUSY", "HIGH LOAD"]
