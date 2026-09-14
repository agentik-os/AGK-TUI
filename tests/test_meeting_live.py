from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = ROOT / "hermes" / "plugins" / "agentik_os"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


registry = load("agk_meeting_registry", MODULE_DIR / "meeting_registry.py")
publication = load("agk_meeting_publication", MODULE_DIR / "meeting_publication.py")
live = load("agk_meeting_live", MODULE_DIR / "meeting_live.py")


class FakeComposioRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute(self, slug: str, data: dict, *, account: str) -> dict:
        self.calls.append((slug, data))
        if slug == "CAL_FETCH_ALL_BOOKINGS":
            return {
                "successful": True,
                "data": {
                    "data": [
                        {
                            "uid": "cal-one",
                            "title": "Cal meeting",
                            "startTime": "2026-08-30T10:00:00Z",
                            "endTime": "2026-08-30T10:30:00Z",
                            "status": "upcoming",
                            "meetingUrl": "https://meet.google.com/abc-defg-hij",
                        }
                    ],
                    "pagination": {"hasNextPage": False},
                },
            }
        raise AssertionError(slug)

    def proxy(self, url: str, *, toolkit: str, account: str) -> dict:
        self.calls.append(("proxy", {"url": url}))
        if "pageToken=next-page" in url:
            return {
                "items": [
                    {
                        "id": "google-two",
                        "summary": "Second meeting",
                        "status": "confirmed",
                        "start": {"dateTime": "2026-08-31T10:00:00Z"},
                        "end": {"dateTime": "2026-08-31T10:30:00Z"},
                    }
                ]
            }
        return {
            "items": [
                {
                    "id": "google-one",
                    "summary": "First meeting",
                    "status": "confirmed",
                    "start": {"dateTime": "2026-08-30T10:00:00Z"},
                    "end": {"dateTime": "2026-08-30T10:30:00Z"},
                }
            ],
            "nextPageToken": "next-page",
        }


def test_composio_source_normalizes_cal_and_paginates_google() -> None:
    runner = FakeComposioRunner()
    source = live.ComposioMeetingSource(
        runner,
        cal_account="cal-safe-selector",
        google_account="google-safe-selector",
    )
    start = datetime(2026, 8, 29, tzinfo=timezone.utc)
    end = datetime(2026, 9, 28, tzinfo=timezone.utc)

    cal = source.fetch_cal(start=start, end=end)
    google = source.fetch_google(start=start, end=end)

    assert [row["uid"] for row in cal["bookings"]] == ["cal-one"]
    assert [row["id"] for row in google["items"]] == ["google-one", "google-two"]
    assert len([call for call in runner.calls if call[0] == "proxy"]) == 2
    encoded_calls = json.dumps(runner.calls).lower()
    for forbidden in ("authorization", "access_token", "bot_token", "bearer "):
        assert forbidden not in encoded_calls


class FakeDiscordTransport:
    def __init__(self) -> None:
        self.messages: dict[tuple[str, str], dict] = {}
        self.channels: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.next_id = 1000

    def request(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path))
        if (
            method == "POST"
            and path == f"/channels/{registry.EVENTS_CHANNEL_ID}/messages"
        ):
            self.next_id += 1
            row = {
                "id": str(self.next_id),
                "channel_id": str(registry.EVENTS_CHANNEL_ID),
                "content": payload["content"],
            }
            self.messages[(str(registry.EVENTS_CHANNEL_ID), row["id"])] = row
            return row
        if method == "PATCH" and path.startswith(
            f"/channels/{registry.EVENTS_CHANNEL_ID}/messages/"
        ):
            message_id = path.rsplit("/", 1)[1]
            row = self.messages[(str(registry.EVENTS_CHANNEL_ID), message_id)]
            row["content"] = payload["content"]
            return row
        if method == "GET" and "/messages/" in path:
            parts = path.split("/")
            return self.messages[(parts[2], parts[4])]
        if (
            method == "POST"
            and path == f"/channels/{registry.MEETINGS_FORUM_ID}/threads"
        ):
            self.next_id += 1
            thread_id = str(self.next_id)
            message_id = str(self.next_id + 10000)
            self.channels[thread_id] = {
                "id": thread_id,
                "parent_id": str(registry.MEETINGS_FORUM_ID),
                "name": payload["name"],
            }
            self.messages[(thread_id, message_id)] = {
                "id": message_id,
                "channel_id": thread_id,
                "content": payload["message"]["content"],
            }
            return {
                **self.channels[thread_id],
                "message": self.messages[(thread_id, message_id)],
            }
        if (
            method == "PATCH"
            and path.startswith("/channels/")
            and "/messages/" not in path
        ):
            thread_id = path.split("/")[2]
            self.channels[thread_id]["name"] = payload["name"]
            return self.channels[thread_id]
        if method == "PATCH" and "/messages/" in path:
            parts = path.split("/")
            row = self.messages[(parts[2], parts[4])]
            row["content"] = payload["content"]
            return row
        if method == "GET" and path.startswith("/channels/"):
            return self.channels[path.split("/")[2]]
        raise AssertionError((method, path, payload))


def test_persistent_discord_client_creates_reads_and_updates_exact_targets(
    tmp_path: Path,
) -> None:
    transport = FakeDiscordTransport()
    client = live.PersistentDiscordMeetingClient(
        transport, tmp_path / "publication-state.json"
    )

    created = client.create_surface(registry.EVENTS_CHANNEL_ID, "upcoming", "first")
    assert client.get_surface(registry.EVENTS_CHANNEL_ID, "upcoming") == created
    updated = client.update_surface(
        registry.EVENTS_CHANNEL_ID,
        created["message_id"],
        "upcoming",
        "second",
    )
    assert updated["content"] == "second"

    post = client.create_forum_post(
        registry.MEETINGS_FORUM_ID,
        "meeting:one",
        "2026-08-30 · Review · completed",
        "report one",
    )
    assert client.get_forum_post(registry.MEETINGS_FORUM_ID, "meeting:one") == post
    updated_post = client.update_forum_post(
        registry.MEETINGS_FORUM_ID,
        post["thread_id"],
        post["message_id"],
        "meeting:one",
        "2026-08-30 · Review · completed",
        "report two",
    )
    assert updated_post["content"] == "report two"
    assert (tmp_path / "publication-state.json").stat().st_mode & 0o777 == 0o600


def test_live_sync_is_idempotent_with_provider_and_discord_seams(
    tmp_path: Path,
) -> None:
    runner = FakeComposioRunner()
    source = live.ComposioMeetingSource(
        runner,
        cal_account="cal-safe-selector",
        google_account="google-safe-selector",
    )
    transport = FakeDiscordTransport()
    client = live.PersistentDiscordMeetingClient(
        transport, tmp_path / "publication-state.json"
    )
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)

    first = live.run_live_sync(
        source=source,
        discord=client,
        registry_path=tmp_path / "registry.json",
        now=now,
        horizon_days=30,
    )
    call_count = len(transport.calls)
    second = live.run_live_sync(
        source=source,
        discord=client,
        registry_path=tmp_path / "registry.json",
        now=now,
        horizon_days=30,
    )

    assert first["registry"] == "updated"
    assert first["discord"]["events"] == "created"
    assert second["registry"] == "unchanged"
    assert second["discord"]["events"] == "unchanged"
    assert len(transport.calls) == call_count + 1  # one exact GET readback, no write
