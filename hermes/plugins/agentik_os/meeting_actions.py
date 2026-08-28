"""Private provider action bindings for canonical meetings."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

try:
    from .meeting_registry import ingest_cal_payload, ingest_google_payload
except ImportError:
    try:
        from meeting_registry import ingest_cal_payload, ingest_google_payload
    except ImportError:
        from agk_meeting_registry import (  # type: ignore[no-redef]
            ingest_cal_payload,
            ingest_google_payload,
        )

SCHEMA = "agk.meeting-actions.v1"


def _canonical_id(
    candidate: dict[str, Any], meetings: list[dict[str, Any]]
) -> str | None:
    identities = set(candidate.get("identity_keys") or [])
    matches = [
        meeting
        for meeting in meetings
        if meeting.get("start") == candidate.get("start")
        and identities.intersection(meeting.get("identity_keys") or [])
    ]
    return str(matches[0]["id"]) if len(matches) == 1 else None


def build_action_map(
    meetings: list[dict[str, Any]],
    *,
    cal_payload: dict[str, Any],
    google_payload: dict[str, Any],
    cal_account: str,
    google_account: str,
) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    cal_rows = cal_payload.get("bookings") if isinstance(cal_payload, dict) else []
    for row in cal_rows if isinstance(cal_rows, list) else []:
        if not isinstance(row, dict) or not row.get("uid"):
            continue
        normalized = ingest_cal_payload({"bookings": [row]})
        meeting_id = _canonical_id(normalized[0], meetings) if normalized else None
        if meeting_id:
            result.setdefault(meeting_id, []).append(
                {
                    "source": "cal",
                    "resource_id": str(row["uid"]),
                    "account": cal_account,
                }
            )
    google_rows = (
        google_payload.get("items") if isinstance(google_payload, dict) else []
    )
    for row in google_rows if isinstance(google_rows, list) else []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        normalized = ingest_google_payload({"items": [row]})
        meeting_id = _canonical_id(normalized[0], meetings) if normalized else None
        if meeting_id:
            result.setdefault(meeting_id, []).append(
                {
                    "source": "google_calendar",
                    "resource_id": str(row["id"]),
                    "account": google_account,
                    "calendar_id": "primary",
                }
            )
    for values in result.values():
        values.sort(
            key=lambda row: (0 if row["source"] == "cal" else 1, row["resource_id"])
        )
    return dict(sorted(result.items()))


class AtomicMeetingActions:
    def __init__(self, path: Path):
        self.path = Path(path)

    def update(self, actions: dict[str, list[dict[str, str]]]) -> bool:
        encoded = (
            json.dumps({"schema": SCHEMA, "actions": actions}, indent=2, sort_keys=True)
            + "\n"
        ).encode()
        try:
            if self.path.read_bytes() == encoded:
                return False
        except FileNotFoundError:
            pass
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return True

    def load(self) -> dict[str, list[dict[str, str]]]:
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if value.get("schema") != SCHEMA or not isinstance(value.get("actions"), dict):
            raise ValueError("unsupported meeting actions schema")
        return value["actions"]
