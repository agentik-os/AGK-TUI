from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = ROOT / "hermes" / "plugins" / "agentik_os"


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


registry_module = load_module("agk_meeting_registry", "meeting_registry.py")
publication = load_module("agk_meeting_publication", "meeting_publication.py")
FIXTURES = Path(__file__).parent / "fixtures" / "meetings"


class FakeDiscordClient:
    def __init__(self) -> None:
        self.surfaces: dict[tuple[int, str], dict] = {}
        self.posts: dict[tuple[int, str], dict] = {}
        self.calls: list[tuple] = []
        self.next_id = 100

    def get_surface(self, channel_id: int, key: str):
        return self.surfaces.get((channel_id, key))

    def create_surface(self, channel_id: int, key: str, content: str):
        self.calls.append(("create_surface", channel_id, key))
        self.next_id += 1
        row = {"message_id": self.next_id, "content": content}
        self.surfaces[(channel_id, key)] = row
        return row

    def update_surface(self, channel_id: int, message_id: int, key: str, content: str):
        self.calls.append(("update_surface", channel_id, message_id, key))
        row = {"message_id": message_id, "content": content}
        self.surfaces[(channel_id, key)] = row
        return row

    def get_forum_post(self, forum_id: int, key: str):
        return self.posts.get((forum_id, key))

    def create_forum_post(self, forum_id: int, key: str, title: str, content: str):
        self.calls.append(("create_forum_post", forum_id, key))
        self.next_id += 1
        row = {
            "thread_id": self.next_id,
            "message_id": self.next_id + 1000,
            "title": title,
            "content": content,
        }
        self.posts[(forum_id, key)] = row
        return row

    def update_forum_post(
        self,
        forum_id: int,
        thread_id: int,
        message_id: int,
        key: str,
        title: str,
        content: str,
    ):
        self.calls.append(("update_forum_post", forum_id, thread_id, message_id, key))
        row = {
            "thread_id": thread_id,
            "message_id": message_id,
            "title": title,
            "content": content,
        }
        self.posts[(forum_id, key)] = row
        return row


class BrokenReadbackClient(FakeDiscordClient):
    def create_forum_post(self, forum_id: int, key: str, title: str, content: str):
        row = super().create_forum_post(forum_id, key, title, content)
        self.posts[(forum_id, key)]["content"] = "wrong"
        return row


def meetings_from_fixtures():
    cal = json.loads((FIXTURES / "cal_bookings.json").read_text())
    google = json.loads((FIXTURES / "google_events.json").read_text())
    return registry_module.merge_meetings(
        [
            *registry_module.ingest_cal_payload(cal),
            *registry_module.ingest_google_payload(google),
        ]
    )


def test_granola_reconciliation_updates_exact_canonical_meeting_idempotently() -> None:
    meetings = meetings_from_fixtures()
    shared = next(item for item in meetings if item["title"] == "Client discovery")
    payload = {
        "meeting_id": shared["id"],
        "summary": "Discussed launch. Bearer secret-token",
        "decisions": ["Launch on Monday"],
        "action_items": [
            {
                "text": "Send plan",
                "owner": "client@example.net",
                "deadline": "2026-09-01",
            }
        ],
        "transcript_url": "https://app.granola.ai/notes/abc?token=secret",
        "event_id": "granola-delivery-1",
    }

    first = publication.reconcile_granola_payload(meetings, payload)
    second = publication.reconcile_granola_payload(meetings, payload)

    assert first == publication.ReconciliationResult(
        status="updated", meeting_id=shared["id"]
    )
    assert second == publication.ReconciliationResult(
        status="unchanged", meeting_id=shared["id"]
    )
    report = shared["reports"]["granola"]
    assert report["summary"] == "Discussed launch. [redacted]"
    assert report["transcript_url"] == "https://app.granola.ai/notes/abc"
    encoded = json.dumps(report)
    assert "secret-token" not in encoded
    assert "client@example.net" not in encoded
    assert "granola-delivery-1" not in encoded


def test_granola_reconciliation_refuses_unmatched_or_ambiguous_payload() -> None:
    meetings = meetings_from_fixtures()
    before = json.dumps(meetings, sort_keys=True)
    result = publication.reconcile_granola_payload(meetings, {"summary": "Unknown"})
    assert result.status == "unmatched"
    assert json.dumps(meetings, sort_keys=True) == before


def test_discord_sync_creates_then_noops_then_updates_canonical_targets() -> None:
    meetings = meetings_from_fixtures()
    completed = next(item for item in meetings if item["title"] == "Client discovery")
    completed["status"] = "completed"
    completed["reports"] = {
        "granola": {
            "summary": "Discovery complete",
            "decisions": ["Proceed"],
            "action_items": [
                {"text": "Send scope", "owner": "[redacted]", "deadline": "2026-09-01"}
            ],
            "transcript_url": "https://app.granola.ai/notes/abc",
            "capture_quality": "available",
        }
    }
    client = FakeDiscordClient()
    now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)

    first = publication.sync_discord(client, meetings, now=now)
    call_count = len(client.calls)
    second = publication.sync_discord(client, meetings, now=now)
    completed["reports"]["granola"]["decisions"].append("Confirm dates")
    third = publication.sync_discord(client, meetings, now=now)

    assert first == {"events": "created", "meeting_posts": {completed["id"]: "created"}}
    assert second == {
        "events": "unchanged",
        "meeting_posts": {completed["id"]: "unchanged"},
    }
    assert len(client.calls) == call_count + 1
    assert third == {
        "events": "unchanged",
        "meeting_posts": {completed["id"]: "updated"},
    }
    assert client.calls[0][1] == registry_module.EVENTS_CHANNEL_ID
    forum_calls = [call for call in client.calls if "forum_post" in call[0]]
    assert all(call[1] == registry_module.MEETINGS_FORUM_ID for call in forum_calls)
    post = client.posts[(registry_module.MEETINGS_FORUM_ID, completed["id"])]
    assert post["title"] == "2026-08-29 · Client discovery · completed"
    assert "Confirm dates" in post["content"]


def test_discord_sync_requires_exact_post_write_readback() -> None:
    meetings = meetings_from_fixtures()
    completed = meetings[0]
    completed["status"] = "completed"
    completed["reports"] = {
        "granola": {"summary": "Done", "decisions": [], "action_items": []}
    }

    try:
        publication.sync_discord(
            BrokenReadbackClient(),
            meetings,
            now=datetime(2026, 8, 29, 8, tzinfo=timezone.utc),
        )
    except publication.DiscordReadbackError as exc:
        assert "forum post" in str(exc)
    else:
        raise AssertionError("missing fail-closed readback error")


def test_completed_meeting_without_granola_report_does_not_publish_fake_summary() -> (
    None
):
    meetings = meetings_from_fixtures()
    completed = meetings[0]
    completed["status"] = "completed"
    client = FakeDiscordClient()

    result = publication.sync_discord(
        client,
        meetings,
        now=datetime(2026, 8, 29, 8, tzinfo=timezone.utc),
    )

    assert result["meeting_posts"] == {}
    assert not client.posts
    assert all(call[0] != "create_forum_post" for call in client.calls)


def test_forum_starter_message_never_exceeds_discord_content_limit() -> None:
    meetings = meetings_from_fixtures()
    completed = meetings[0]
    completed["status"] = "completed"
    completed["reports"] = {
        "granola": {
            "summary": "summary " * 700,
            "decisions": ["decision " * 100 for _ in range(20)],
            "action_items": [
                {
                    "text": "action " * 100,
                    "owner": "owner",
                    "deadline": "2026-09-01",
                }
                for _ in range(20)
            ],
            "capture_quality": "available",
        }
    }
    client = FakeDiscordClient()

    publication.sync_discord(
        client,
        meetings,
        now=datetime(2026, 8, 29, 8, tzinfo=timezone.utc),
    )

    post = client.posts[(registry_module.MEETINGS_FORUM_ID, completed["id"])]
    assert len(post["content"]) <= 2000
