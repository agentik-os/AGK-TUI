"""Owner-confirmed meeting mutations through connected Composio accounts."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


class ActionRunner(Protocol):
    def execute(
        self, slug: str, data: dict[str, Any], *, account: str
    ) -> dict[str, Any]: ...


def meeting_id_for_thread(state_path: Path, thread_id: int) -> str | None:
    try:
        state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if state.get("schema") != "agk.meeting-publication-state.v1":
        return None
    prefix = "1542526162062938152:"
    for key, row in (state.get("posts") or {}).items():
        if (
            key.startswith(prefix)
            and isinstance(row, dict)
            and row.get("thread_id") == thread_id
        ):
            return key[len(prefix) :]
    return None


def _find(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find(child, key)
            if found is not None:
                return found
    return None


def _successful(value: dict[str, Any]) -> bool:
    return value.get("successful", True) is True and not value.get("error")


def _choose(bindings: list[dict[str, str]]) -> dict[str, str]:
    for source in ("cal", "google_calendar"):
        for binding in bindings:
            if binding.get("source") == source:
                return binding
    raise ValueError("meeting has no actionable provider binding")


class MeetingActionCoordinator:
    def __init__(self, runner: ActionRunner):
        self.runner = runner

    def cancel(self, bindings: list[dict[str, str]], *, reason: str) -> dict[str, str]:
        binding = _choose(bindings)
        resource_id = binding["resource_id"]
        account = binding["account"]
        if binding["source"] == "cal":
            result = self.runner.execute(
                "CAL_CANCEL_BOOKING_VIA_UID",
                {
                    "bookingUid": resource_id,
                    "cancellationReason": reason[:500],
                    "cancelSubsequentBookings": False,
                },
                account=account,
            )
            if not _successful(result):
                raise RuntimeError("Cal.com cancellation failed")
            readback = self.runner.execute(
                "CAL_RETRIEVE_BOOKING_DETAILS_BY_UID",
                {"bookingUid": resource_id},
                account=account,
            )
            if str(_find(readback, "status") or "").casefold() not in {
                "cancelled",
                "canceled",
            }:
                raise RuntimeError("Cal.com cancellation readback failed")
            return {"source": "cal", "status": "cancelled"}
        result = self.runner.execute(
            "GOOGLECALENDAR_DELETE_EVENT",
            {
                "event_id": resource_id,
                "calendar_id": binding.get("calendar_id", "primary"),
                "send_updates": "all",
            },
            account=account,
        )
        if not _successful(result):
            raise RuntimeError("Google Calendar cancellation failed")
        return {"source": "google_calendar", "status": "cancelled"}

    def reschedule(
        self, bindings: list[dict[str, str]], *, start: str
    ) -> dict[str, str]:
        parsed = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("reschedule start must include timezone")
        normalized = parsed.isoformat().replace("+00:00", "Z")
        binding = _choose(bindings)
        resource_id = binding["resource_id"]
        account = binding["account"]
        if binding["source"] == "cal":
            result = self.runner.execute(
                "CAL_RESCHEDULE_BOOKING_BY_UID",
                {"bookingUid": resource_id, "start": normalized},
                account=account,
            )
            if not _successful(result):
                raise RuntimeError("Cal.com reschedule failed")
            readback = self.runner.execute(
                "CAL_RETRIEVE_BOOKING_DETAILS_BY_UID",
                {"bookingUid": resource_id},
                account=account,
            )
        else:
            calendar_id = binding.get("calendar_id", "primary")
            result = self.runner.execute(
                "GOOGLECALENDAR_PATCH_EVENT",
                {
                    "calendar_id": calendar_id,
                    "event_id": resource_id,
                    "start_time": normalized,
                    "send_updates": "all",
                },
                account=account,
            )
            if not _successful(result):
                raise RuntimeError("Google Calendar reschedule failed")
            readback = self.runner.execute(
                "GOOGLECALENDAR_EVENTS_GET",
                {"calendar_id": calendar_id, "event_id": resource_id},
                account=account,
            )
        observed = _find(readback, "dateTime") or _find(readback, "startTime")
        if str(observed or "").replace("+00:00", "Z") != normalized:
            raise RuntimeError("meeting reschedule readback failed")
        return {
            "source": binding["source"],
            "status": "rescheduled",
            "start": normalized,
        }
