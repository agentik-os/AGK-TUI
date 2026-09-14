from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "meeting_registry_sync.py"
FIXTURES = ROOT / "tests" / "fixtures" / "meetings"


def test_fixture_cli_writes_registry_and_is_idempotent(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    command = [
        sys.executable,
        str(SCRIPT),
        "--cal-payload",
        str(FIXTURES / "cal_bookings.json"),
        "--google-payload",
        str(FIXTURES / "google_events.json"),
        "--registry",
        str(registry),
        "--now",
        "2026-08-29T08:00:00Z",
    ]

    first = subprocess.run(
        command, cwd=ROOT, check=True, text=True, capture_output=True
    )
    second = subprocess.run(
        command, cwd=ROOT, check=True, text=True, capture_output=True
    )

    assert first.stderr == ""
    assert first.stdout.startswith("registry=updated meetings=4\n## Upcoming meetings")
    assert second.stdout.startswith(
        "registry=unchanged meetings=4\n## Upcoming meetings"
    )
    document = json.loads(registry.read_text())
    assert document["schema"] == "agk.meeting-registry.v1"
    assert len(document["meetings"]) == 4


def test_systemd_templates_run_live_five_minute_sync_without_secret_arguments() -> None:
    service = (ROOT / "systemd" / "agk-meeting-registry.service.in").read_text()
    timer = (ROOT / "systemd" / "agk-meeting-registry.timer").read_text()

    assert "meeting_registry_live.py" in service
    assert "--cal-payload" not in service and "--google-payload" not in service
    assert "1542526162062938152" not in service
    assert "token" not in service.casefold()
    assert "OnUnitActiveSec=5min" in timer
    assert "Persistent=true" in timer
    assert "enable" not in service.casefold() + timer.casefold()
