from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = ROOT / "hermes" / "plugins" / "agentik_os"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


control = load("agk_meeting_control", "meeting_control.py")


class FakeRunner:
    def __init__(self):
        self.calls = []

    def execute(self, slug, data, *, account):
        self.calls.append((slug, data, account))
        if slug == "CAL_CANCEL_BOOKING_VIA_UID":
            return {"successful": True}
        if slug == "CAL_RETRIEVE_BOOKING_DETAILS_BY_UID":
            return {"successful": True, "data": {"status": "cancelled"}}
        if slug == "GOOGLECALENDAR_PATCH_EVENT":
            return {"successful": True}
        if slug == "GOOGLECALENDAR_EVENTS_GET":
            return {
                "successful": True,
                "data": {"start": {"dateTime": "2026-09-01T10:00:00Z"}},
            }
        raise AssertionError(slug)


def test_thread_resolution_uses_private_publication_state(tmp_path):
    state = tmp_path / "publication.json"
    state.write_text(
        json.dumps(
            {
                "schema": "agk.meeting-publication-state.v1",
                "surfaces": {},
                "posts": {
                    "1542526162062938152:meeting:abc": {
                        "thread_id": 123,
                        "message_id": 456,
                    }
                },
            }
        )
    )
    assert control.meeting_id_for_thread(state, 123) == "meeting:abc"
    assert control.meeting_id_for_thread(state, 999) is None


def test_cancel_prefers_cal_and_requires_cancelled_readback():
    runner = FakeRunner()
    coordinator = control.MeetingActionCoordinator(runner)
    bindings = [
        {
            "source": "google_calendar",
            "resource_id": "google-id",
            "account": "google",
            "calendar_id": "primary",
        },
        {"source": "cal", "resource_id": "cal-uid", "account": "cal"},
    ]

    result = coordinator.cancel(bindings, reason="Owner canceled from Discord")

    assert result == {"source": "cal", "status": "cancelled"}
    assert runner.calls[0] == (
        "CAL_CANCEL_BOOKING_VIA_UID",
        {
            "bookingUid": "cal-uid",
            "cancellationReason": "Owner canceled from Discord",
            "cancelSubsequentBookings": False,
        },
        "cal",
    )
    assert runner.calls[1][0] == "CAL_RETRIEVE_BOOKING_DETAILS_BY_UID"


def test_reschedule_google_occurrence_and_reads_new_start():
    runner = FakeRunner()
    coordinator = control.MeetingActionCoordinator(runner)
    bindings = [
        {
            "source": "google_calendar",
            "resource_id": "google-id",
            "account": "google",
            "calendar_id": "primary",
        }
    ]

    result = coordinator.reschedule(bindings, start="2026-09-01T10:00:00Z")

    assert result == {
        "source": "google_calendar",
        "status": "rescheduled",
        "start": "2026-09-01T10:00:00Z",
    }
    assert runner.calls[0] == (
        "GOOGLECALENDAR_PATCH_EVENT",
        {
            "calendar_id": "primary",
            "event_id": "google-id",
            "start_time": "2026-09-01T10:00:00Z",
            "send_updates": "all",
        },
        "google",
    )
    assert runner.calls[1][0] == "GOOGLECALENDAR_EVENTS_GET"
