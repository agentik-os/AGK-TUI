from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "meeting_registry_live.py"


def load_script():
    spec = importlib.util.spec_from_file_location("meeting_registry_live_cli", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_command_runner_uses_account_selector_and_never_secret_flags() -> None:
    module = load_script()
    calls: list[list[str]] = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout='{"successful":true}', stderr=""
        )

    runner = module.CommandComposioRunner(("/safe/composio",), run=run)
    assert runner.execute(
        "CAL_FETCH_ALL_BOOKINGS", {"take": 1}, account="cal-safe"
    ) == {"successful": True}
    assert runner.proxy(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        toolkit="googlecalendar",
        account="google-safe",
    ) == {"successful": True}

    encoded = json.dumps(calls).lower()
    assert "cal-safe" in encoded and "google-safe" in encoded
    for forbidden in ("authorization", "access_token", "bot_token", "bearer "):
        assert forbidden not in encoded


def test_discord_transport_keeps_token_only_in_authorization_header() -> None:
    module = load_script()
    observed = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"id":"123","channel_id":"456","content":"ok"}'

    def open_request(request, timeout):
        observed["url"] = request.full_url
        observed["headers"] = dict(request.header_items())
        observed["data"] = request.data
        observed["timeout"] = timeout
        return Response()

    transport = module.DiscordRestTransport("private-token", open_request=open_request)
    row = transport.request("POST", "/channels/456/messages", {"content": "ok"})

    assert row["id"] == "123"
    assert observed["headers"]["Authorization"] == "Bot private-token"
    assert b"private-token" not in observed["data"]
    assert "private-token" not in observed["url"]


def test_discord_transport_maps_get_404_to_missing_resource() -> None:
    module = load_script()

    def open_request(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    transport = module.DiscordRestTransport("private-token", open_request=open_request)
    with pytest.raises(KeyError):
        transport.request("GET", "/channels/456/messages/123")


def test_live_cli_imports_in_a_fresh_python_process() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Synchronize Cal.com and Google Calendar" in result.stdout


def test_systemd_service_runs_live_mode_without_fixture_inputs() -> None:
    service = (ROOT / "systemd" / "agk-meeting-registry.service.in").read_text()
    timer = (ROOT / "systemd" / "agk-meeting-registry.timer").read_text()

    assert "meeting_registry_live.py" in service
    assert "meeting-input" not in service
    assert "EnvironmentFile=/home/operator/.hermes/.env" in service
    assert "ProtectHome=read-only" in service
    assert "OnUnitActiveSec=5min" in timer
