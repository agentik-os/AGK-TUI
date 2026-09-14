"""Source-only Meeting Registry normalization, persistence, and rendering.

The module intentionally accepts already-authorized provider payloads and has no
credential or network access. Persisted and rendered values are allowlisted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

MEETINGS_FORUM_ID = 1542526162062938152
EVENTS_CHANNEL_ID = 1542526309211570226
SCHEMA = "agk.meeting-registry.v1"

_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_SECRET_RE = re.compile(
    r"(?i)\b(?:bearer\s+\S+|(?:api[_ -]?key|password|passwd|secret|token)\s*[:=]\s*\S+)"
)
_PLATFORM_LABELS = {
    "google_meet": "Google Meet",
    "zoom": "Zoom",
    "microsoft_teams": "Microsoft Teams",
}


def _safe_text(value: Any, *, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    text = _EMAIL_RE.sub("[redacted]", text)
    text = _SECRET_RE.sub("[redacted]", text)
    return text[:limit] or "Untitled meeting"


def _identity(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"identity:{digest}"


def _source_ref(source: str, value: Any, kind: str) -> dict[str, str]:
    return {"source": source, "kind": kind, "digest": _identity(value).split(":", 1)[1]}


def _identity_key(kind: str, value: Any) -> str:
    digest = hashlib.sha256(
        str(value or "").strip().casefold().encode("utf-8")
    ).hexdigest()[:24]
    return f"{kind}:{digest}"


def _iso_datetime(value: Any) -> str:
    text = str(value or "").strip()
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("meeting datetime must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def classify_meeting_link(value: Any) -> dict[str, str] | None:
    """Return an allowlisted platform and a query/fragment-free HTTPS URL."""
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme.casefold() != "https" or not host:
        return None
    if host == "meet.google.com":
        platform = "google_meet"
    elif host == "zoom.us" or host.endswith(".zoom.us"):
        platform = "zoom"
    elif host in {"teams.microsoft.com", "teams.live.com"}:
        platform = "microsoft_teams"
    else:
        return None
    safe_url = urlunsplit(
        ("https", parsed.netloc.casefold(), parsed.path or "/", "", "")
    )
    return {"platform": platform, "url": safe_url}


def _first_link(*values: Any) -> dict[str, str] | None:
    for value in values:
        if isinstance(value, list):
            candidates = value
        else:
            candidates = [value]
        for candidate in candidates:
            link = classify_meeting_link(candidate)
            if link:
                return link
    return None


def _base_meeting(
    *,
    source: str,
    uid: Any,
    uid_kind: str,
    title: Any,
    start: Any,
    end: Any,
    organizer: Any,
    participants: Iterable[Any],
    join: dict[str, str] | None,
    status: Any,
    identity_priority: int,
    additional_identities: Iterable[tuple[str, Any]] = (),
) -> dict[str, Any]:
    primary_key = _identity_key(uid_kind, uid)
    identity_keys = [
        primary_key,
        *(_identity_key(kind, value) for kind, value in additional_identities if value),
    ]
    canonical_id = "meeting:" + primary_key.split(":", 1)[1]
    participant_ids = sorted(
        {_identity(item) for item in participants if str(item or "").strip()}
    )
    normalized_status = str(status or "scheduled").strip().casefold()
    if normalized_status in {"accepted", "confirmed"}:
        normalized_status = "scheduled"
    return {
        "id": canonical_id,
        "identity_keys": sorted(set(identity_keys)),
        "identity_priority": identity_priority,
        "source_refs": [_source_ref(source, uid, uid_kind)],
        "title": _safe_text(title),
        "start": _iso_datetime(start),
        "end": _iso_datetime(end),
        "organizer": _identity(organizer),
        "participants": participant_ids,
        "join": join,
        "armed": join is not None,
        "status": normalized_status,
        "warnings": [],
    }


def ingest_cal_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a fixture-shaped Cal.com bookings response."""
    rows = payload.get("bookings", []) if isinstance(payload, dict) else []
    meetings: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        destination_uid = row.get("eventUid") or row.get("destinationCalendarEventUid")
        uid = destination_uid or row.get("uid")
        if not uid:
            continue
        organizer = (
            row.get("organizer") if isinstance(row.get("organizer"), dict) else {}
        )
        attendees = (
            row.get("attendees") if isinstance(row.get("attendees"), list) else []
        )
        meetings.append(
            _base_meeting(
                source="cal",
                uid=uid,
                uid_kind="calendar_uid" if destination_uid else "cal_booking_uid",
                title=row.get("title"),
                start=row.get("startTime"),
                end=row.get("endTime"),
                organizer=organizer.get("email", ""),
                participants=[
                    item.get("email", "")
                    for item in attendees
                    if isinstance(item, dict)
                ],
                join=_first_link(row.get("location"), row.get("meetingUrl")),
                status=row.get("status"),
                identity_priority=2 if destination_uid else 3,
            )
        )
    return meetings


def ingest_google_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a fixture-shaped Google Calendar events response."""
    rows = payload.get("items", []) if isinstance(payload, dict) else []
    meetings: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        provider_uid = row.get("id")
        calendar_uid = row.get("iCalUID")
        uid = provider_uid or calendar_uid
        if not uid:
            continue
        organizer = (
            row.get("organizer") if isinstance(row.get("organizer"), dict) else {}
        )
        attendees = (
            row.get("attendees") if isinstance(row.get("attendees"), list) else []
        )
        conference = (
            row.get("conferenceData")
            if isinstance(row.get("conferenceData"), dict)
            else {}
        )
        entry_points = (
            conference.get("entryPoints")
            if isinstance(conference.get("entryPoints"), list)
            else []
        )
        conference_urls = [
            item.get("uri")
            for item in entry_points
            if isinstance(item, dict) and item.get("entryPointType") in {None, "video"}
        ]
        start = row.get("start") if isinstance(row.get("start"), dict) else {}
        end = row.get("end") if isinstance(row.get("end"), dict) else {}
        meetings.append(
            _base_meeting(
                source="google_calendar",
                uid=uid,
                uid_kind="google_event_uid" if provider_uid else "calendar_uid",
                title=row.get("summary"),
                start=start.get("dateTime") or start.get("date"),
                end=end.get("dateTime") or end.get("date"),
                organizer=organizer.get("email", ""),
                participants=[
                    item.get("email", "")
                    for item in attendees
                    if isinstance(item, dict)
                ],
                join=_first_link(
                    conference_urls, row.get("hangoutLink"), row.get("location")
                ),
                status=row.get("status"),
                identity_priority=1 if provider_uid else 2,
                additional_identities=(("calendar_uid", calendar_uid),),
            )
        )
    return meetings


def _merge_pair(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    target["identity_keys"] = sorted(
        set(target["identity_keys"]) | set(incoming["identity_keys"])
    )
    refs = {
        json.dumps(item, sort_keys=True): item
        for item in [*target["source_refs"], *incoming["source_refs"]]
    }
    target["source_refs"] = [refs[key] for key in sorted(refs)]
    target["participants"] = sorted(
        set(target["participants"]) | set(incoming["participants"])
    )
    target["join"] = target["join"] or incoming["join"]
    target["armed"] = target["join"] is not None
    if incoming.get("identity_priority", 99) < target.get("identity_priority", 99):
        target["id"] = incoming["id"]
        target["identity_priority"] = incoming["identity_priority"]


def merge_meetings(meetings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate exact identities, then deterministic call/start/organizer identities."""
    merged: list[dict[str, Any]] = []
    identity_index: dict[str, dict[str, Any]] = {}
    call_index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for meeting in sorted(meetings, key=lambda item: (item["start"], item["id"])):
        target = next(
            (
                identity_index[key]
                for key in meeting["identity_keys"]
                if key in identity_index
                and (
                    not key.startswith("calendar_uid:")
                    or identity_index[key]["start"] == meeting["start"]
                )
            ),
            None,
        )
        if target is None and meeting.get("join"):
            call_key = (meeting["join"]["url"], meeting["start"], meeting["organizer"])
            target = call_index.get(call_key)
        if target is None:
            target = json.loads(json.dumps(meeting))
            merged.append(target)
        else:
            _merge_pair(target, meeting)
        for key in target["identity_keys"]:
            identity_index[key] = target
        if target.get("join"):
            call_index[
                (target["join"]["url"], target["start"], target["organizer"])
            ] = target
    for index, first in enumerate(merged):
        for second in merged[index + 1 :]:
            participant_overlap = bool(
                set(first["participants"]) & set(second["participants"])
            )
            same_context = (
                first["start"] == second["start"]
                and first["organizer"] == second["organizer"]
            )
            if same_context and participant_overlap:
                first["warnings"] = sorted(
                    set(first["warnings"]) | {"possible_duplicate"}
                )
                second["warnings"] = sorted(
                    set(second["warnings"]) | {"possible_duplicate"}
                )
    return sorted(merged, key=lambda item: (item["start"], item["id"]))


class AtomicMeetingRegistry:
    """Private, deterministic atomic JSON registry with no-op idempotency."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def update(self, meetings: Iterable[dict[str, Any]]) -> bool:
        document = {"schema": SCHEMA, "meetings": merge_meetings(meetings)}
        encoded = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        try:
            if self.path.read_bytes() == encoded:
                return False
        except FileNotFoundError:
            pass
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return True

    def load(self) -> list[dict[str, Any]]:
        document = json.loads(self.path.read_text(encoding="utf-8"))
        if document.get("schema") != SCHEMA or not isinstance(
            document.get("meetings"), list
        ):
            raise ValueError("unsupported meeting registry schema")
        return document["meetings"]


def render_upcoming_events(
    meetings: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    limit: int = 12,
) -> str:
    """Render a compact, deterministic message suitable for edit-in-place publishing."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    rows = []
    for meeting in meetings:
        start = datetime.fromisoformat(meeting["start"].replace("Z", "+00:00"))
        if start >= current.astimezone(timezone.utc) and meeting.get("status") not in {
            "cancelled",
            "canceled",
        }:
            rows.append((start, meeting))
    lines = ["## Upcoming meetings", ""]
    for start, meeting in sorted(rows, key=lambda item: (item[0], item[1]["id"]))[
        :limit
    ]:
        join = meeting.get("join")
        call = _PLATFORM_LABELS[join["platform"]] if join else "no supported call link"
        lines.append(
            f"<t:{int(start.timestamp())}:f> · **{_safe_text(meeting['title'], limit=100)}** · {call}"
        )
    if len(lines) == 2:
        lines.append("No upcoming meetings.")
    lines.extend(["", "Updated from the canonical Meeting Registry."])
    return "\n".join(lines)[:2000]
