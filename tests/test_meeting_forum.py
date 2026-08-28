from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = ROOT / "hermes" / "plugins" / "agentik_os"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


registry = load("agk_meeting_registry", "meeting_registry.py")
forum = load("agk_meeting_forum", "meeting_forum.py")


def meeting(**changes):
    row = {
        "id": "meeting:abc123",
        "title": "Weekly review",
        "start": "2026-08-30T10:00:00Z",
        "end": "2026-08-30T11:00:00Z",
        "status": "scheduled",
        "armed": True,
        "join": {
            "platform": "google_meet",
            "url": "https://meet.google.com/abc-defg-hij",
        },
        "source_refs": [
            {"source": "google_calendar", "kind": "google_event_uid", "digest": "abc"}
        ],
        "warnings": [],
    }
    row.update(changes)
    return row


def test_status_tags_cover_upcoming_in_progress_past_and_canceled() -> None:
    assert (
        forum.meeting_lifecycle(
            meeting(), now=datetime(2026, 8, 30, 9, tzinfo=timezone.utc)
        )
        == "Upcoming"
    )
    assert (
        forum.meeting_lifecycle(
            meeting(), now=datetime(2026, 8, 30, 10, 30, tzinfo=timezone.utc)
        )
        == "In progress"
    )
    assert (
        forum.meeting_lifecycle(
            meeting(), now=datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
        )
        == "Past"
    )
    assert (
        forum.meeting_lifecycle(
            meeting(status="cancelled"),
            now=datetime(2026, 8, 30, 9, tzinfo=timezone.utc),
        )
        == "Canceled"
    )
    assert forum.meeting_tags(
        meeting(reports={"granola": {"summary": "Done"}}),
        now=datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
    ) == ["Past", "Report ready"]
    assert forum.meeting_tags(
        meeting(), now=datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    ) == ["Past", "Recording missing"]


def test_forum_selection_excludes_cancelled_noise_but_updates_existing_cancelled_post() -> (
    None
):
    now = datetime(2026, 8, 30, 9, tzinfo=timezone.utc)
    upcoming = meeting(id="meeting:upcoming")
    cancelled_new = meeting(id="meeting:cancelled-new", status="cancelled")
    cancelled_existing = meeting(id="meeting:cancelled-existing", status="cancelled")
    unarmed = meeting(id="meeting:focus", armed=False, join=None)

    selected = forum.select_forum_meetings(
        [upcoming, cancelled_new, cancelled_existing, unarmed],
        existing_ids={"meeting:cancelled-existing"},
        now=now,
    )

    assert [row["id"] for row in selected] == [
        "meeting:cancelled-existing",
        "meeting:upcoming",
    ]


def test_forum_starter_and_components_are_compact_and_actionable() -> None:
    now = datetime(2026, 8, 30, 9, tzinfo=timezone.utc)
    title, content = forum.render_forum_post(meeting(), now=now)
    components = forum.meeting_components(meeting(), lifecycle="Upcoming")

    assert title == "2026-08-30 · Weekly review"
    assert "<t:" in content
    assert "Google Meet" in content
    assert "Granola" in content
    assert len(content) <= 2000
    buttons = components[0]["components"]
    assert [
        (button.get("label"), button.get("custom_id"), button.get("url"))
        for button in buttons
    ] == [
        ("Join", None, "https://meet.google.com/abc-defg-hij"),
        ("Refresh", "agkmeet:refresh", None),
        ("Reschedule", "agkmeet:reschedule", None),
        ("Cancel", "agkmeet:cancel", None),
        ("Granola", "agkmeet:granola", None),
    ]
    assert all("meeting:abc123" not in json.dumps(button) for button in buttons)


class FakeForumClient:
    def __init__(self):
        self.tags = {}
        self.posts = {}
        self.calls = []

    def ensure_forum_tags(self, forum_id, names):
        self.calls.append(("ensure_tags", forum_id, tuple(names)))
        self.tags = {name: str(index + 1) for index, name in enumerate(names)}
        return self.tags

    def list_forum_post_ids(self, forum_id):
        return set(self.posts)

    def get_forum_control_post(self, forum_id, key):
        return self.posts.get(key)

    def create_forum_control_post(
        self, forum_id, key, title, content, tag_ids, components
    ):
        self.calls.append(("create", key))
        row = {
            "thread_id": 100 + len(self.posts),
            "message_id": 200 + len(self.posts),
            "title": title,
            "content": content,
            "tag_ids": list(tag_ids),
            "components": components,
        }
        self.posts[key] = row
        return row

    def update_forum_control_post(
        self, forum_id, key, thread_id, message_id, title, content, tag_ids, components
    ):
        self.calls.append(("update", key))
        row = {
            "thread_id": thread_id,
            "message_id": message_id,
            "title": title,
            "content": content,
            "tag_ids": list(tag_ids),
            "components": components,
        }
        self.posts[key] = row
        return row


def test_forum_sync_creates_then_updates_same_conversation_and_tags() -> None:
    client = FakeForumClient()
    now = datetime(2026, 8, 30, 9, tzinfo=timezone.utc)
    row = meeting()

    first = forum.sync_meeting_forum(client, [row], now=now)
    second = forum.sync_meeting_forum(client, [row], now=now)
    past = forum.sync_meeting_forum(
        client,
        [row],
        now=datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
    )

    assert first == {"meeting:abc123": "created"}
    assert second == {"meeting:abc123": "unchanged"}
    assert past == {"meeting:abc123": "updated"}
    assert client.posts["meeting:abc123"]["tag_ids"] == ["3", "6"]
    assert [call[0] for call in client.calls].count("create") == 1
