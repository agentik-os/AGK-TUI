from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "hermes" / "plugins" / "agentik_os" / "meeting_registry.py"
SPEC = importlib.util.spec_from_file_location("meeting_registry_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
meeting_registry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(meeting_registry)

EVENTS_CHANNEL_ID = meeting_registry.EVENTS_CHANNEL_ID
MEETINGS_FORUM_ID = meeting_registry.MEETINGS_FORUM_ID
AtomicMeetingRegistry = meeting_registry.AtomicMeetingRegistry
classify_meeting_link = meeting_registry.classify_meeting_link
ingest_cal_payload = meeting_registry.ingest_cal_payload
ingest_google_payload = meeting_registry.ingest_google_payload
merge_meetings = meeting_registry.merge_meetings
render_upcoming_events = meeting_registry.render_upcoming_events

FIXTURES = Path(__file__).parent / "fixtures" / "meetings"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_target_constants_are_exact() -> None:
    assert MEETINGS_FORUM_ID == 1542526162062938152
    assert EVENTS_CHANNEL_ID == 1542526309211570226


def test_supported_link_classification_is_allowlisted_and_strips_secrets() -> None:
    assert classify_meeting_link("https://meet.google.com/abc-defg-hij?authuser=1") == {
        "platform": "google_meet",
        "url": "https://meet.google.com/abc-defg-hij",
    }
    assert classify_meeting_link("https://us02web.zoom.us/j/123?pwd=secret") == {
        "platform": "zoom",
        "url": "https://us02web.zoom.us/j/123",
    }
    assert classify_meeting_link(
        "https://teams.microsoft.com/l/meetup-join/abc?context=secret"
    ) == {
        "platform": "microsoft_teams",
        "url": "https://teams.microsoft.com/l/meetup-join/abc",
    }
    assert classify_meeting_link("https://meet.google.com.evil.test/abc") is None
    assert classify_meeting_link("javascript:alert(1)") is None


def test_fixture_ingest_dedupes_provider_identity_and_redacts_private_data() -> None:
    cal = ingest_cal_payload(load_fixture("cal_bookings.json"))
    google = ingest_google_payload(load_fixture("google_events.json"))
    meetings = merge_meetings([*cal, *google])

    assert len(meetings) == 4
    shared = next(item for item in meetings if item["title"] == "Client discovery")
    assert {ref["source"] for ref in shared["source_refs"]} == {
        "cal",
        "google_calendar",
    }
    assert shared["join"]["platform"] == "google_meet"
    assert shared["join"]["url"] == "https://meet.google.com/abc-defg-hij"
    assert shared["organizer"].startswith("identity:")
    assert shared["participants"][0].startswith("identity:")
    focus = next(item for item in meetings if item["title"] == "Focus block")
    assert focus["join"] is None
    assert focus["armed"] is False

    encoded = json.dumps(meetings)
    for secret in (
        "must-never-leak",
        "private-token",
        "super-secret",
        "client@example.net",
        "owner@agentik-os.com",
        "shared-event@example.com",
        "google-id-1",
        "cal-booking-100",
    ):
        assert secret not in encoded.lower()


def test_ambiguous_time_participant_candidates_remain_separate_with_warnings() -> None:
    base = ingest_google_payload(load_fixture("google_events.json"))[0]
    first = json.loads(json.dumps(base))
    second = json.loads(json.dumps(base))
    first["join"] = None
    first["armed"] = False
    second["join"] = None
    second["armed"] = False
    first["id"] = "meeting:first"
    first["identity_keys"] = ["calendar_uid:first"]
    second["id"] = "meeting:second"
    second["identity_keys"] = ["calendar_uid:second"]

    merged = merge_meetings([first, second])

    assert len(merged) == 2
    assert all("possible_duplicate" in item["warnings"] for item in merged)


def test_recurring_google_occurrences_keep_distinct_provider_instances() -> None:
    payload = {
        "items": [
            {
                "id": "recurring-event_20260829T090000Z",
                "iCalUID": "recurring-event@example.com",
                "summary": "Weekly operating review",
                "status": "confirmed",
                "start": {"dateTime": "2026-08-29T09:00:00Z"},
                "end": {"dateTime": "2026-08-29T09:30:00Z"},
                "hangoutLink": "https://meet.google.com/abc-defg-hij",
            },
            {
                "id": "recurring-event_20260905T090000Z",
                "iCalUID": "recurring-event@example.com",
                "summary": "Weekly operating review",
                "status": "confirmed",
                "start": {"dateTime": "2026-09-05T09:00:00Z"},
                "end": {"dateTime": "2026-09-05T09:30:00Z"},
                "hangoutLink": "https://meet.google.com/abc-defg-hij",
            },
        ]
    }

    merged = merge_meetings(ingest_google_payload(payload))

    assert len(merged) == 2
    assert {row["start"] for row in merged} == {
        "2026-08-29T09:00:00Z",
        "2026-09-05T09:00:00Z",
    }


def test_cancelled_occurrences_never_render_as_upcoming() -> None:
    payload = {
        "items": [
            {
                "id": "cancelled-instance",
                "iCalUID": "series@example.com",
                "summary": "Cancelled review",
                "status": "cancelled",
                "start": {"dateTime": "2026-08-30T09:00:00Z"},
                "end": {"dateTime": "2026-08-30T09:30:00Z"},
                "hangoutLink": "https://meet.google.com/abc-defg-hij",
            }
        ]
    }

    rendered = render_upcoming_events(
        merge_meetings(ingest_google_payload(payload)),
        now=datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc),
    )

    assert "Cancelled review" not in rendered
    assert "No upcoming meetings." in rendered


def test_atomic_registry_update_is_idempotent_and_private(tmp_path: Path) -> None:
    target = tmp_path / "meeting-registry.json"
    registry = AtomicMeetingRegistry(target)
    meetings = merge_meetings(
        [
            *ingest_cal_payload(load_fixture("cal_bookings.json")),
            *ingest_google_payload(load_fixture("google_events.json")),
        ]
    )

    assert registry.update(meetings) is True
    first = target.read_bytes()
    first_inode = target.stat().st_ino
    assert registry.update(list(reversed(meetings))) is False
    assert target.read_bytes() == first
    assert target.stat().st_ino == first_inode
    assert os.stat(target).st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".*.tmp"))


def test_upcoming_events_message_is_stable_compact_and_redacted() -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
    meetings = merge_meetings(
        [
            *ingest_cal_payload(load_fixture("cal_bookings.json")),
            *ingest_google_payload(load_fixture("google_events.json")),
        ]
    )
    rendered = render_upcoming_events(meetings, now=now)

    assert rendered.startswith("## Upcoming meetings")
    assert "Client discovery" in rendered
    assert "Google Meet" in rendered
    assert "Focus block" in rendered and "no supported call link" in rendered
    assert "1542526309211570226" not in rendered
    assert "@example" not in rendered
    assert len(rendered) <= 2000
