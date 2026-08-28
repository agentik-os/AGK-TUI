#!/usr/bin/env python3
"""Build a private Meeting Registry from local Cal.com/Google fixture payloads."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1] / "hermes" / "plugins" / "agentik_os"
sys.path.insert(0, str(MODULE_DIR))

from meeting_registry import (
    AtomicMeetingRegistry,
    ingest_cal_payload,
    ingest_google_payload,
    merge_meetings,
    render_upcoming_events,
)


def _payload(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"payload must be a JSON object: {path.name}")
    return value


def _timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--now must include a timezone")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cal-payload", type=Path, required=True)
    parser.add_argument("--google-payload", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument(
        "--now", help="timezone-aware ISO timestamp; defaults to current UTC time"
    )
    args = parser.parse_args(argv)

    meetings = merge_meetings(
        [
            *ingest_cal_payload(_payload(args.cal_payload)),
            *ingest_google_payload(_payload(args.google_payload)),
        ]
    )
    changed = AtomicMeetingRegistry(args.registry).update(meetings)
    print(f"registry={'updated' if changed else 'unchanged'} meetings={len(meetings)}")
    print(render_upcoming_events(meetings, now=_timestamp(args.now)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
