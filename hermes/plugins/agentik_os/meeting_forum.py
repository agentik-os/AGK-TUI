"""Canonical Discord Meetings forum lifecycle, tags, and controls."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Protocol

try:
    from .meeting_registry import MEETINGS_FORUM_ID, _safe_text
except ImportError:
    try:
        from meeting_registry import MEETINGS_FORUM_ID, _safe_text
    except ImportError:
        from agk_meeting_registry import (  # type: ignore[no-redef]
            MEETINGS_FORUM_ID,
            _safe_text,
        )

FORUM_TAG_NAMES = (
    "Upcoming",
    "In progress",
    "Past",
    "Canceled",
    "Report ready",
    "Recording missing",
)
_PLATFORM_LABELS = {
    "google_meet": "Google Meet",
    "zoom": "Zoom",
    "microsoft_teams": "Microsoft Teams",
}


class MeetingForumClient(Protocol):
    def ensure_forum_tags(
        self, forum_id: int, names: Iterable[str]
    ) -> dict[str, str]: ...
    def list_forum_post_ids(self, forum_id: int) -> set[str]: ...
    def get_forum_control_post(
        self, forum_id: int, key: str
    ) -> dict[str, Any] | None: ...
    def create_forum_control_post(
        self,
        forum_id: int,
        key: str,
        title: str,
        content: str,
        tag_ids: list[str],
        components: list[dict[str, Any]],
    ) -> dict[str, Any]: ...
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
    ) -> dict[str, Any]: ...


def _when(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("meeting timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def meeting_lifecycle(meeting: dict[str, Any], *, now: datetime) -> str:
    status = str(meeting.get("status") or "").casefold()
    if status in {"cancelled", "canceled"}:
        return "Canceled"
    current = now.astimezone(timezone.utc)
    start = _when(meeting["start"])
    end = _when(meeting["end"])
    if current < start:
        return "Upcoming"
    if current < end:
        return "In progress"
    return "Past"


def meeting_tags(meeting: dict[str, Any], *, now: datetime) -> list[str]:
    lifecycle = meeting_lifecycle(meeting, now=now)
    tags = [lifecycle]
    if lifecycle == "Past":
        report = meeting.get("reports", {}).get("granola")
        tags.append(
            "Report ready"
            if isinstance(report, dict) and report
            else "Recording missing"
        )
    return tags


def select_forum_meetings(
    meetings: Iterable[dict[str, Any]],
    *,
    existing_ids: set[str],
    now: datetime,
) -> list[dict[str, Any]]:
    selected = []
    for meeting in meetings:
        meeting_id = str(meeting.get("id") or "")
        lifecycle = meeting_lifecycle(meeting, now=now)
        if meeting_id in existing_ids or (
            meeting.get("armed") is True and lifecycle != "Canceled"
        ):
            selected.append(meeting)
    return sorted(selected, key=lambda row: str(row.get("id") or ""))


def render_forum_post(meeting: dict[str, Any], *, now: datetime) -> tuple[str, str]:
    start = _when(meeting["start"])
    end = _when(meeting["end"])
    lifecycle = meeting_lifecycle(meeting, now=now)
    join = meeting.get("join") if isinstance(meeting.get("join"), dict) else None
    platform = _PLATFORM_LABELS.get(str((join or {}).get("platform")), "Meeting")
    sources = sorted(
        {
            "Cal.com" if ref.get("source") == "cal" else "Google Calendar"
            for ref in meeting.get("source_refs", [])
            if isinstance(ref, dict)
        }
    )
    report = meeting.get("reports", {}).get("granola")
    granola = (
        "Report ready"
        if isinstance(report, dict) and report
        else "Waiting for recording"
    )
    title = (
        f"{start.date().isoformat()} · {_safe_text(meeting.get('title'), limit=75)}"[
            :100
        ]
    )
    content = "\n".join(
        [
            f"## {_safe_text(meeting.get('title'), limit=120)}",
            "",
            f"<t:{int(start.timestamp())}:F> → <t:{int(end.timestamp())}:t>",
            f"Status: **{lifecycle}**",
            f"Source: {', '.join(sources) or 'Calendar'}",
            f"Call: {platform}",
            f"Granola: {granola}",
            "",
            "Use the controls below. Cancel and Reschedule require owner confirmation.",
            "The meeting report and follow-up conversation stay in this post.",
        ]
    )
    return title, content[:2000]


def meeting_components(
    meeting: dict[str, Any], *, lifecycle: str
) -> list[dict[str, Any]]:
    join = meeting.get("join") if isinstance(meeting.get("join"), dict) else None
    buttons: list[dict[str, Any]] = []
    if join and join.get("url"):
        buttons.append({"type": 2, "style": 5, "label": "Join", "url": join["url"]})
    disabled = lifecycle in {"Past", "Canceled"}
    buttons.extend(
        [
            {"type": 2, "style": 2, "label": "Refresh", "custom_id": "agkmeet:refresh"},
            {
                "type": 2,
                "style": 1,
                "label": "Reschedule",
                "custom_id": "agkmeet:reschedule",
                "disabled": disabled,
            },
            {
                "type": 2,
                "style": 4,
                "label": "Cancel",
                "custom_id": "agkmeet:cancel",
                "disabled": disabled,
            },
            {"type": 2, "style": 2, "label": "Granola", "custom_id": "agkmeet:granola"},
        ]
    )
    return [{"type": 1, "components": buttons[:5]}]


def sync_meeting_forum(
    client: MeetingForumClient,
    meetings: Iterable[dict[str, Any]],
    *,
    now: datetime,
) -> dict[str, str]:
    tag_map = client.ensure_forum_tags(MEETINGS_FORUM_ID, FORUM_TAG_NAMES)
    existing_ids = client.list_forum_post_ids(MEETINGS_FORUM_ID)
    result: dict[str, str] = {}
    for meeting in select_forum_meetings(meetings, existing_ids=existing_ids, now=now):
        key = str(meeting["id"])
        title, content = render_forum_post(meeting, now=now)
        lifecycle = meeting_lifecycle(meeting, now=now)
        tag_ids = [tag_map[name] for name in meeting_tags(meeting, now=now)]
        components = meeting_components(meeting, lifecycle=lifecycle)
        existing = client.get_forum_control_post(MEETINGS_FORUM_ID, key)
        expected = {
            "title": title,
            "content": content,
            "tag_ids": tag_ids,
            "components": components,
        }
        if existing and all(
            existing.get(field) == value for field, value in expected.items()
        ):
            result[key] = "unchanged"
            continue
        if existing:
            client.update_forum_control_post(
                MEETINGS_FORUM_ID,
                key,
                int(existing["thread_id"]),
                int(existing["message_id"]),
                title,
                content,
                tag_ids,
                components,
            )
            result[key] = "updated"
        else:
            client.create_forum_control_post(
                MEETINGS_FORUM_ID,
                key,
                title,
                content,
                tag_ids,
                components,
            )
            result[key] = "created"
    return result
