from __future__ import annotations

import importlib.util
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


registry = load("agk_meeting_registry", "meeting_registry.py")
actions = load("agk_meeting_actions", "meeting_actions.py")


def test_action_map_binds_raw_provider_ids_privately_to_canonical_meeting(tmp_path):
    cal_payload = {
        "bookings": [
            {
                "uid": "cal-booking-private",
                "eventUid": "shared-calendar-uid",
                "title": "Review",
                "startTime": "2026-08-30T10:00:00Z",
                "endTime": "2026-08-30T10:30:00Z",
                "status": "upcoming",
                "meetingUrl": "https://meet.google.com/abc-defg-hij",
            }
        ]
    }
    google_payload = {
        "items": [
            {
                "id": "google-event-private",
                "iCalUID": "shared-calendar-uid",
                "summary": "Review",
                "status": "confirmed",
                "start": {"dateTime": "2026-08-30T10:00:00Z"},
                "end": {"dateTime": "2026-08-30T10:30:00Z"},
                "hangoutLink": "https://meet.google.com/abc-defg-hij",
            }
        ]
    }
    meetings = registry.merge_meetings(
        [
            *registry.ingest_cal_payload(cal_payload),
            *registry.ingest_google_payload(google_payload),
        ]
    )

    mapping = actions.build_action_map(
        meetings,
        cal_payload=cal_payload,
        google_payload=google_payload,
        cal_account="cal-account",
        google_account="google-account",
    )
    target = tmp_path / "actions.json"
    store = actions.AtomicMeetingActions(target)

    assert store.update(mapping) is True
    assert store.update(mapping) is False
    loaded = store.load()[meetings[0]["id"]]
    assert loaded == [
        {
            "source": "cal",
            "resource_id": "cal-booking-private",
            "account": "cal-account",
        },
        {
            "source": "google_calendar",
            "resource_id": "google-event-private",
            "account": "google-account",
            "calendar_id": "primary",
        },
    ]
    assert target.stat().st_mode & 0o777 == 0o600
