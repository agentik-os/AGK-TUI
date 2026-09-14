"""Granola reconciliation and idempotent Discord publication seams.

No transport or authentication is implemented here. Callers inject authorized,
source-specific clients implementing the protocols below.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, TypedDict
from urllib.parse import urlsplit, urlunsplit

try:
    from .meeting_registry import (
        EVENTS_CHANNEL_ID,
        MEETINGS_FORUM_ID,
        _safe_text,
        render_upcoming_events,
    )
except ImportError:  # Direct loading for the installed runner or focused tests.
    try:
        from meeting_registry import (  # type: ignore[no-redef]
            EVENTS_CHANNEL_ID,
            MEETINGS_FORUM_ID,
            _safe_text,
            render_upcoming_events,
        )
    except ImportError:
        from agk_meeting_registry import (  # type: ignore[no-redef]
            EVENTS_CHANNEL_ID,
            MEETINGS_FORUM_ID,
            _safe_text,
            render_upcoming_events,
        )

EVENTS_SURFACE_KEY = "agk-meeting-registry-upcoming"


class GranolaPayload(TypedDict, total=False):
    meeting_id: str
    summary: str
    decisions: list[str]
    action_items: list[dict[str, str]]
    transcript_url: str
    capture_quality: str
    event_id: str


class GranolaPayloadSource(Protocol):
    """Authorized adapter boundary; implementations may fetch, this module does not."""

    def fetch_payloads(self) -> Iterable[GranolaPayload]: ...


class DiscordMeetingClient(Protocol):
    """Minimal injected discord.py adapter seam used by the synchronizer."""

    def get_surface(self, channel_id: int, key: str) -> dict[str, Any] | None: ...
    def create_surface(
        self, channel_id: int, key: str, content: str
    ) -> dict[str, Any]: ...
    def update_surface(
        self, channel_id: int, message_id: int, key: str, content: str
    ) -> dict[str, Any]: ...
    def get_forum_post(self, forum_id: int, key: str) -> dict[str, Any] | None: ...
    def create_forum_post(
        self, forum_id: int, key: str, title: str, content: str
    ) -> dict[str, Any]: ...
    def update_forum_post(
        self,
        forum_id: int,
        thread_id: int,
        message_id: int,
        key: str,
        title: str,
        content: str,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ReconciliationResult:
    status: str
    meeting_id: str | None


class DiscordReadbackError(RuntimeError):
    """Raised when the canonical exact-target write cannot be verified."""


def _granola_url(value: Any) -> str | None:
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme.casefold() != "https" or host not in {
        "granola.ai",
        "app.granola.ai",
    }:
        return None
    return urlunsplit(("https", parsed.netloc.casefold(), parsed.path or "/", "", ""))


def _granola_report(payload: GranolaPayload) -> dict[str, Any]:
    decisions = [
        _safe_text(item, limit=500)
        for item in payload.get("decisions", [])
        if isinstance(item, str) and item.strip()
    ][:50]
    action_items: list[dict[str, str]] = []
    for item in payload.get("action_items", [])[:50]:
        if not isinstance(item, dict):
            continue
        action_items.append(
            {
                "text": _safe_text(item.get("text"), limit=500),
                "owner": _safe_text(item.get("owner"), limit=100),
                "deadline": _safe_text(item.get("deadline"), limit=40),
            }
        )
    report: dict[str, Any] = {
        "summary": _safe_text(payload.get("summary"), limit=2000),
        "decisions": decisions,
        "action_items": action_items,
        "capture_quality": _safe_text(
            payload.get("capture_quality") or "available", limit=40
        ),
    }
    transcript_url = _granola_url(payload.get("transcript_url"))
    if transcript_url:
        report["transcript_url"] = transcript_url
    return report


def reconcile_granola_payload(
    meetings: list[dict[str, Any]],
    payload: GranolaPayload,
) -> ReconciliationResult:
    """Apply an exact canonical-ID Granola report; never perform a fuzzy merge."""
    meeting_id = str(payload.get("meeting_id") or "")
    matches = [meeting for meeting in meetings if meeting.get("id") == meeting_id]
    if len(matches) != 1:
        return ReconciliationResult(
            "ambiguous" if len(matches) > 1 else "unmatched", None
        )
    meeting = matches[0]
    report = _granola_report(payload)
    reports = meeting.setdefault("reports", {})
    if reports.get("granola") == report:
        return ReconciliationResult("unchanged", meeting_id)
    reports["granola"] = report
    return ReconciliationResult("updated", meeting_id)


def _meeting_post(meeting: dict[str, Any]) -> tuple[str, str]:
    date = str(meeting["start"])[:10]
    title = f"{date} · {_safe_text(meeting.get('title'), limit=65)} · completed"[:100]
    report = meeting.get("reports", {}).get("granola", {})
    lines = [f"## {_safe_text(meeting.get('title'), limit=120)}", "", "### Summary"]
    lines.append(
        _safe_text(report.get("summary") or "Summary unavailable.", limit=2000)
    )
    lines.extend(["", "### Decisions"])
    decisions = (
        report.get("decisions") if isinstance(report.get("decisions"), list) else []
    )
    lines.extend(f"- {_safe_text(item, limit=500)}" for item in decisions)
    if not decisions:
        lines.append("- None recorded.")
    lines.extend(["", "### Action items"])
    actions = (
        report.get("action_items")
        if isinstance(report.get("action_items"), list)
        else []
    )
    for action in actions:
        if not isinstance(action, dict):
            continue
        owner = _safe_text(action.get("owner") or "unassigned", limit=100)
        deadline = _safe_text(action.get("deadline") or "no deadline", limit=40)
        lines.append(
            f"- {_safe_text(action.get('text'), limit=500)} · {owner} · {deadline}"
        )
    if not actions:
        lines.append("- None recorded.")
    transcript = _granola_url(report.get("transcript_url"))
    lines.extend(
        [
            "",
            f"Capture quality: `{_safe_text(report.get('capture_quality') or 'unknown', limit=40)}`",
        ]
    )
    if transcript:
        lines.append(f"Granola source: {transcript}")
    content = "\n".join(lines)
    if len(content) > 2000:
        content = content[:1999].rstrip() + "…"
    return title, content


def _verify_surface(client: DiscordMeetingClient, content: str) -> None:
    row = client.get_surface(EVENTS_CHANNEL_ID, EVENTS_SURFACE_KEY)
    if (
        not row
        or row.get("content") != content
        or not isinstance(row.get("message_id"), int)
    ):
        raise DiscordReadbackError("events surface exact-target readback failed")


def _sync_events(client: DiscordMeetingClient, content: str) -> str:
    existing = client.get_surface(EVENTS_CHANNEL_ID, EVENTS_SURFACE_KEY)
    if existing and existing.get("content") == content:
        return "unchanged"
    if existing:
        client.update_surface(
            EVENTS_CHANNEL_ID,
            int(existing["message_id"]),
            EVENTS_SURFACE_KEY,
            content,
        )
        status = "updated"
    else:
        client.create_surface(EVENTS_CHANNEL_ID, EVENTS_SURFACE_KEY, content)
        status = "created"
    _verify_surface(client, content)
    return status


def _verify_post(
    client: DiscordMeetingClient, key: str, title: str, content: str
) -> None:
    row = client.get_forum_post(MEETINGS_FORUM_ID, key)
    if (
        not row
        or row.get("title") != title
        or row.get("content") != content
        or not isinstance(row.get("thread_id"), int)
        or not isinstance(row.get("message_id"), int)
    ):
        raise DiscordReadbackError("forum post exact-target readback failed")


def _sync_post(client: DiscordMeetingClient, meeting: dict[str, Any]) -> str:
    key = str(meeting["id"])
    title, content = _meeting_post(meeting)
    existing = client.get_forum_post(MEETINGS_FORUM_ID, key)
    if (
        existing
        and existing.get("title") == title
        and existing.get("content") == content
    ):
        return "unchanged"
    if existing:
        client.update_forum_post(
            MEETINGS_FORUM_ID,
            int(existing["thread_id"]),
            int(existing["message_id"]),
            key,
            title,
            content,
        )
        status = "updated"
    else:
        client.create_forum_post(MEETINGS_FORUM_ID, key, title, content)
        status = "created"
    _verify_post(client, key, title, content)
    return status


def sync_discord(
    client: DiscordMeetingClient,
    meetings: Iterable[dict[str, Any]],
    *,
    now: datetime,
) -> dict[str, Any]:
    """Create/update canonical Discord surfaces and verify every write by readback."""
    rows = list(meetings)
    result: dict[str, Any] = {
        "events": _sync_events(client, render_upcoming_events(rows, now=now)),
        "meeting_posts": {},
    }
    for meeting in sorted(rows, key=lambda item: (item["start"], item["id"])):
        granola = meeting.get("reports", {}).get("granola")
        if (
            meeting.get("status") == "completed"
            and isinstance(granola, dict)
            and granola
        ):
            result["meeting_posts"][meeting["id"]] = _sync_post(client, meeting)
    return result
