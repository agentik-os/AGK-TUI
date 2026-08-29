"""Production seams for Composio meeting reads and exact Discord publication.

Secrets stay in the owning process environment. This module receives only stable
connected-account selectors and an injected transport/runner.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

try:
    from .meeting_actions import AtomicMeetingActions, build_action_map
    from .meeting_forum import sync_meeting_forum
    from .meeting_publication import sync_discord
    from .meeting_registry import (
        AtomicMeetingRegistry,
        ingest_cal_payload,
        ingest_google_payload,
        merge_meetings,
    )
except ImportError:  # Direct loading for the installed runner or focused tests.
    try:
        from meeting_actions import (  # type: ignore[no-redef]
            AtomicMeetingActions,
            build_action_map,
        )
        from meeting_forum import sync_meeting_forum  # type: ignore[no-redef]
        from meeting_publication import sync_discord  # type: ignore[no-redef]
        from meeting_registry import (  # type: ignore[no-redef]
            AtomicMeetingRegistry,
            ingest_cal_payload,
            ingest_google_payload,
            merge_meetings,
        )
    except ImportError:
        from agk_meeting_actions import (  # type: ignore[no-redef]
            AtomicMeetingActions,
            build_action_map,
        )
        from agk_meeting_forum import sync_meeting_forum  # type: ignore[no-redef]
        from agk_meeting_publication import sync_discord  # type: ignore[no-redef]
        from agk_meeting_registry import (  # type: ignore[no-redef]
            AtomicMeetingRegistry,
            ingest_cal_payload,
            ingest_google_payload,
            merge_meetings,
        )

PUBLICATION_SCHEMA = "agk.meeting-publication-state.v1"


class ComposioRunner(Protocol):
    def execute(
        self, slug: str, data: dict[str, Any], *, account: str
    ) -> dict[str, Any]: ...

    def proxy(self, url: str, *, toolkit: str, account: str) -> dict[str, Any]: ...


class DiscordTransport(Protocol):
    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("meeting sync timestamps must include a timezone")
    return value.astimezone(timezone.utc)


def _rfc3339(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


class ComposioMeetingSource:
    """Bounded, paginated read-only provider adapter."""

    def __init__(
        self,
        runner: ComposioRunner,
        *,
        cal_account: str,
        google_account: str,
    ) -> None:
        if not cal_account or not google_account:
            raise ValueError("connected-account selectors are required")
        self.runner = runner
        self.cal_account = cal_account
        self.google_account = google_account

    def fetch_cal(self, *, start: datetime, end: datetime) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        skip = 0
        while True:
            result = self.runner.execute(
                "CAL_FETCH_ALL_BOOKINGS",
                {
                    "status": ["upcoming", "unconfirmed", "cancelled"],
                    "take": 100,
                    "skip": skip,
                    "sortStart": "asc",
                    "afterStart": _rfc3339(start),
                    "beforeEnd": _rfc3339(end),
                },
                account=self.cal_account,
            )
            if result.get("successful") is not True:
                raise RuntimeError("Cal.com read failed")
            outer = result.get("data")
            data = outer if isinstance(outer, Mapping) else {}
            page = data.get("data")
            if isinstance(page, list):
                rows.extend(item for item in page if isinstance(item, dict))
            pagination = data.get("pagination")
            if not isinstance(pagination, Mapping) or not pagination.get("hasNextPage"):
                break
            if not page:
                raise RuntimeError("Cal.com pagination made no progress")
            skip += len(page)
        return {"bookings": rows}

    def fetch_google(self, *, start: datetime, end: datetime) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        page_token = ""
        seen_tokens: set[str] = set()
        while True:
            query: dict[str, str] = {
                "timeMin": _rfc3339(start),
                "timeMax": _rfc3339(end),
                "maxResults": "2500",
                "singleEvents": "true",
                "orderBy": "startTime",
                "showDeleted": "true",
            }
            if page_token:
                query["pageToken"] = page_token
            url = (
                "https://www.googleapis.com/calendar/v3/calendars/primary/events?"
                + urlencode(query)
            )
            result = self.runner.proxy(
                url,
                toolkit="googlecalendar",
                account=self.google_account,
            )
            if result.get("error"):
                raise RuntimeError("Google Calendar read failed")
            page = result.get("items")
            if isinstance(page, list):
                rows.extend(item for item in page if isinstance(item, dict))
            next_token = str(result.get("nextPageToken") or "")
            if not next_token:
                break
            if next_token in seen_tokens:
                raise RuntimeError("Google Calendar pagination loop")
            seen_tokens.add(next_token)
            page_token = next_token
        return {"items": rows}


class PersistentDiscordMeetingClient:
    """Discord client seam with exact-target readback and private persisted IDs."""

    def __init__(self, transport: DiscordTransport, state_path: Path) -> None:
        self.transport = transport
        self.state_path = Path(state_path)

    def _load_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"schema": PUBLICATION_SCHEMA, "surfaces": {}, "posts": {}}
        if value.get("schema") != PUBLICATION_SCHEMA:
            raise ValueError("unsupported meeting publication state")
        if not isinstance(value.get("surfaces"), dict) or not isinstance(
            value.get("posts"), dict
        ):
            raise TypeError("invalid meeting publication state")
        return value

    def _save_state(self, value: dict[str, Any]) -> None:
        encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
        self.state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(
            prefix=f".{self.state_path.name}.",
            suffix=".tmp",
            dir=self.state_path.parent,
        )
        temporary = Path(name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.state_path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _surface_key(channel_id: int, key: str) -> str:
        return f"{channel_id}:{key}"

    @staticmethod
    def _post_key(forum_id: int, key: str) -> str:
        return f"{forum_id}:{key}"

    def get_surface(self, channel_id: int, key: str) -> dict[str, Any] | None:
        state = self._load_state()
        state_key = self._surface_key(channel_id, key)
        saved = state["surfaces"].get(state_key)
        if not isinstance(saved, dict) or not isinstance(saved.get("message_id"), int):
            return None
        message_id = saved["message_id"]
        try:
            row = self.transport.request(
                "GET", f"/channels/{channel_id}/messages/{message_id}"
            )
        except KeyError:
            state["surfaces"].pop(state_key, None)
            self._save_state(state)
            return None
        if str(row.get("channel_id")) != str(channel_id) or str(row.get("id")) != str(
            message_id
        ):
            raise RuntimeError("Discord events target readback mismatch")
        return {"message_id": message_id, "content": str(row.get("content") or "")}

    def create_surface(self, channel_id: int, key: str, content: str) -> dict[str, Any]:
        row = self.transport.request(
            "POST",
            f"/channels/{channel_id}/messages",
            {"content": content, "allowed_mentions": {"parse": []}},
        )
        message_id = int(row["id"])
        state = self._load_state()
        state["surfaces"][self._surface_key(channel_id, key)] = {
            "message_id": message_id
        }
        self._save_state(state)
        return {"message_id": message_id, "content": str(row.get("content") or "")}

    def update_surface(
        self, channel_id: int, message_id: int, key: str, content: str
    ) -> dict[str, Any]:
        row = self.transport.request(
            "PATCH",
            f"/channels/{channel_id}/messages/{message_id}",
            {"content": content, "allowed_mentions": {"parse": []}},
        )
        return {"message_id": message_id, "content": str(row.get("content") or "")}

    def get_forum_post(self, forum_id: int, key: str) -> dict[str, Any] | None:
        state = self._load_state()
        state_key = self._post_key(forum_id, key)
        saved = state["posts"].get(state_key)
        if not isinstance(saved, dict):
            return None
        thread_id = saved.get("thread_id")
        message_id = saved.get("message_id")
        if not isinstance(thread_id, int) or not isinstance(message_id, int):
            return None
        try:
            thread = self.transport.request("GET", f"/channels/{thread_id}")
            message = self.transport.request(
                "GET", f"/channels/{thread_id}/messages/{message_id}"
            )
        except KeyError:
            state["posts"].pop(state_key, None)
            self._save_state(state)
            return None
        if (
            str(thread.get("id")) != str(thread_id)
            or str(thread.get("parent_id")) != str(forum_id)
            or str(message.get("id")) != str(message_id)
            or str(message.get("channel_id")) != str(thread_id)
        ):
            raise RuntimeError("Discord forum target readback mismatch")
        return {
            "thread_id": thread_id,
            "message_id": message_id,
            "title": str(thread.get("name") or ""),
            "content": str(message.get("content") or ""),
        }

    def create_forum_post(
        self, forum_id: int, key: str, title: str, content: str
    ) -> dict[str, Any]:
        row = self.transport.request(
            "POST",
            f"/channels/{forum_id}/threads",
            {
                "name": title,
                "auto_archive_duration": 10080,
                "message": {
                    "content": content,
                    "allowed_mentions": {"parse": []},
                },
            },
        )
        message = row.get("message")
        if not isinstance(message, dict):
            raise TypeError("Discord forum creation omitted starter message")
        thread_id = int(row["id"])
        message_id = int(message["id"])
        state = self._load_state()
        state["posts"][self._post_key(forum_id, key)] = {
            "thread_id": thread_id,
            "message_id": message_id,
        }
        self._save_state(state)
        return {
            "thread_id": thread_id,
            "message_id": message_id,
            "title": str(row.get("name") or ""),
            "content": str(message.get("content") or ""),
        }

    def update_forum_post(
        self,
        forum_id: int,
        thread_id: int,
        message_id: int,
        key: str,
        title: str,
        content: str,
    ) -> dict[str, Any]:
        thread = self.transport.request(
            "PATCH", f"/channels/{thread_id}", {"name": title}
        )
        message = self.transport.request(
            "PATCH",
            f"/channels/{thread_id}/messages/{message_id}",
            {"content": content, "allowed_mentions": {"parse": []}},
        )
        return {
            "thread_id": thread_id,
            "message_id": message_id,
            "title": str(thread.get("name") or ""),
            "content": str(message.get("content") or ""),
        }

    def ensure_forum_tags(self, forum_id: int, names: Iterable[str]) -> dict[str, str]:
        desired = list(names)
        channel = self.transport.request("GET", f"/channels/{forum_id}")
        rows = channel.get("available_tags")
        existing = rows if isinstance(rows, list) else []
        by_name = {
            str(row.get("name")): str(row.get("id"))
            for row in existing
            if isinstance(row, dict) and row.get("name") and row.get("id")
        }
        missing = [name for name in desired if name not in by_name]
        if missing:
            channel = self.transport.request(
                "PATCH",
                f"/channels/{forum_id}",
                {
                    "available_tags": [
                        *[row for row in existing if isinstance(row, dict)],
                        *({"name": name, "moderated": False} for name in missing),
                    ]
                },
            )
            by_name = {
                str(row.get("name")): str(row.get("id"))
                for row in channel.get("available_tags", [])
                if isinstance(row, dict) and row.get("name") and row.get("id")
            }
        if any(name not in by_name for name in desired):
            raise RuntimeError("Discord forum tags readback failed")
        return {name: by_name[name] for name in desired}

    def list_forum_post_ids(self, forum_id: int) -> set[str]:
        prefix = f"{forum_id}:"
        return {
            key[len(prefix) :]
            for key in self._load_state()["posts"]
            if key.startswith(prefix)
        }

    def get_forum_control_post(self, forum_id: int, key: str) -> dict[str, Any] | None:
        base = self.get_forum_post(forum_id, key)
        if base is None:
            return None
        thread = self.transport.request("GET", f"/channels/{base['thread_id']}")
        message = self.transport.request(
            "GET", f"/channels/{base['thread_id']}/messages/{base['message_id']}"
        )
        return {
            **base,
            "tag_ids": [str(value) for value in thread.get("applied_tags", [])],
            "components": message.get("components") or [],
        }

    def create_forum_control_post(
        self,
        forum_id: int,
        key: str,
        title: str,
        content: str,
        tag_ids: list[str],
        components: list[dict[str, Any]],
    ) -> dict[str, Any]:
        row = self.transport.request(
            "POST",
            f"/channels/{forum_id}/threads",
            {
                "name": title,
                "auto_archive_duration": 10080,
                "applied_tags": tag_ids,
                "message": {
                    "content": content,
                    "components": components,
                    "allowed_mentions": {"parse": []},
                },
            },
        )
        message = row.get("message")
        if not isinstance(message, dict):
            raise TypeError("Discord forum creation omitted starter message")
        thread_id = int(row["id"])
        message_id = int(message["id"])
        state = self._load_state()
        state["posts"][self._post_key(forum_id, key)] = {
            "thread_id": thread_id,
            "message_id": message_id,
        }
        self._save_state(state)
        return {
            "thread_id": thread_id,
            "message_id": message_id,
            "title": str(row.get("name") or ""),
            "content": str(message.get("content") or ""),
            "tag_ids": [str(value) for value in row.get("applied_tags", [])],
            "components": message.get("components") or [],
        }

    def update_forum_control_post(
        self,
        forum_id: int,
        key: str,
        thread_id: int,
        message_id: int,
        title: str,
        content: str,
        tag_ids: list[str],
        components: list[dict[str, Any]],
    ) -> dict[str, Any]:
        thread = self.transport.request(
            "PATCH",
            f"/channels/{thread_id}",
            {"name": title, "applied_tags": tag_ids, "archived": False},
        )
        message = self.transport.request(
            "PATCH",
            f"/channels/{thread_id}/messages/{message_id}",
            {
                "content": content,
                "components": components,
                "allowed_mentions": {"parse": []},
            },
        )
        return {
            "thread_id": thread_id,
            "message_id": message_id,
            "title": str(thread.get("name") or ""),
            "content": str(message.get("content") or ""),
            "tag_ids": [str(value) for value in thread.get("applied_tags", [])],
            "components": message.get("components") or [],
        }


def run_live_sync(
    *,
    source: ComposioMeetingSource,
    discord: PersistentDiscordMeetingClient,
    registry_path: Path,
    now: datetime,
    actions_path: Path | None = None,
    horizon_days: int = 30,
) -> dict[str, Any]:
    if not 1 <= horizon_days <= 90:
        raise ValueError("horizon_days must be between 1 and 90")
    start = _utc(now)
    end = start + timedelta(days=horizon_days)
    cal_payload = source.fetch_cal(start=start, end=end)
    google_payload = source.fetch_google(start=start, end=end)
    meetings = merge_meetings(
        [
            *ingest_cal_payload(cal_payload),
            *ingest_google_payload(google_payload),
        ]
    )
    changed = AtomicMeetingRegistry(registry_path).update(meetings)
    actions_changed = AtomicMeetingActions(
        actions_path or registry_path.with_name("actions.json")
    ).update(
        build_action_map(
            meetings,
            cal_payload=cal_payload,
            google_payload=google_payload,
            cal_account=source.cal_account,
            google_account=source.google_account,
        )
    )
    return {
        "registry": "updated" if changed else "unchanged",
        "actions": "updated" if actions_changed else "unchanged",
        "meeting_count": len(meetings),
        "discord": {"events": "disabled", "meeting_posts": {}},
        "forum": sync_meeting_forum(discord, meetings, now=start),
    }
