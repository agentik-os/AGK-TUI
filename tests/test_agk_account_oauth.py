import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OAUTH_MODULE = ROOT / "hermes/plugins/platforms/discord/agk_account_oauth.py"
RUNNER_MODULE = ROOT / "scripts/agk_provider_oauth_runner.py"


def load_module(name: str, path: Path):
    assert path.exists(), f"{path.name} does not exist"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture
def oauth():
    return load_module("agk_account_oauth", OAUTH_MODULE)


@pytest.fixture
def runner_script():
    return load_module("agk_provider_oauth_runner", RUNNER_MODULE)


class FakeSystemd:
    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        if argv[:4] == ["systemctl", "--user", "is-active", "--quiet"]:
            return 3
        return 0


def test_only_one_live_attempt_per_provider_and_nickname(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    first = store.create("openai-codex", "add", "Agentik", None, 1441423462492016821)
    second = store.create("openai-codex", "add", "Agentik", None, 1441423462492016821)

    assert store.get(first.attempt_id).status == "cancelled"
    assert store.get(second.attempt_id).status == "pending"


def test_attempt_store_is_durable_mode_safe_and_contains_only_metadata(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create(
        "anthropic", "reconnect", "Loumna", "credential-42", 7,
        guild_id=1541131439599386644, channel_id=99,
    )

    reloaded = oauth.OAuthAttemptStore(tmp_path).get(attempt.attempt_id)
    assert reloaded == attempt
    assert store.path == tmp_path / "state/account-oauth/attempts.json"
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert set(payload) == {"attempts"}
    assert "token" not in store.path.read_text(encoding="utf-8").lower()
    assert "code#state" not in store.path.read_text(encoding="utf-8")


def test_store_rejects_non_allowlisted_provider_and_secret_shaped_metadata(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    with pytest.raises(ValueError):
        store.create("openai", "add", "Agentik", None, 7)
    with pytest.raises(ValueError):
        store.create("anthropic", "add", "sk-secret", None, 7)
    with pytest.raises(ValueError):
        store.create("anthropic", "add", "Loumna", "sk-secret", 7)


def test_start_uses_one_allowlisted_sibling_unit_without_secrets_in_argv(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create(
        "openai-codex", "add", "Agentik", None, 1441423462492016821,
        channel_id=11,
    )
    systemd = FakeSystemd()
    runner = oauth.OAuthRunner(store, systemd, runner_script=RUNNER_MODULE)

    started = runner.start(attempt.attempt_id)

    assert started.status == "running"
    assert started.runner_unit == f"agk-account-oauth-{attempt.attempt_id}.service"
    assert len(systemd.calls) == 1
    argv = systemd.calls[0]
    assert argv[:4] == ["systemd-run", "--user", "--unit", started.runner_unit]
    assert "--provider" in argv and argv[argv.index("--provider") + 1] == "openai-codex"
    assert "--alias" in argv and argv[argv.index("--alias") + 1] == "Agentik"
    assert "--timeout" in argv and argv[argv.index("--timeout") + 1] == "900"
    joined = " ".join(argv).lower()
    assert "code#state" not in joined
    assert "token" not in joined
    assert "password" not in joined


def test_claude_code_submission_rejects_wrong_owner_channel_or_expired_attempt(
    tmp_path, oauth
):
    now = [1000.0]
    store = oauth.OAuthAttemptStore(tmp_path, clock=lambda: now[0])
    attempt = store.create(
        "anthropic", "add", "Loumna", None, 1441423462492016821, channel_id=44
    )
    writes = []
    runner = oauth.OAuthRunner(store, FakeSystemd(), fifo_writer=lambda path, value: writes.append((path, value)))

    assert runner.submit_claude_code(
        attempt.attempt_id, "code#state", user_id=7, channel_id=44
    ) is False
    assert runner.submit_claude_code(
        attempt.attempt_id, "code#state", user_id=1441423462492016821, channel_id=1
    ) is False
    now[0] = attempt.expires_at
    assert runner.submit_claude_code(
        attempt.attempt_id, "code#state", user_id=1441423462492016821, channel_id=44
    ) is False
    assert writes == []
    assert "code#state" not in store.path.read_text(encoding="utf-8")


def test_valid_claude_code_is_written_only_to_fifo_and_never_retained(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("anthropic", "add", "Loumna", None, 7, channel_id=44)
    writes = []
    def complete_write(path, value):
        writes.append((path, value))
        return len(value.encode("utf-8"))

    runner = oauth.OAuthRunner(store, FakeSystemd(), fifo_writer=complete_write)

    assert runner.submit_claude_code(attempt.attempt_id, "code#state", user_id=7, channel_id=44)
    assert writes == [(runner.fifo_path(attempt), "code#state\n")]
    assert "code#state" not in store.path.read_text(encoding="utf-8")
    assert store.get(attempt.attempt_id).status == "code-submitted"


def test_cancel_stops_only_recorded_unit_and_removes_ephemeral_files(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("anthropic", "add", "Loumna", None, 7, channel_id=44)
    systemd = FakeSystemd()
    runner = oauth.OAuthRunner(store, systemd)
    running = store.update(
        attempt.attempt_id,
        status="running",
        runner_unit=f"agk-account-oauth-{attempt.attempt_id}.service",
    )
    fifo = runner.fifo_path(running)
    result = runner.result_path(running)
    fifo.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(fifo, 0o600)
    result.write_text('{"status":"pending"}', encoding="utf-8")

    assert runner.cancel(attempt.attempt_id) is True
    assert systemd.calls[:2] == [
        ["systemctl", "--user", "stop", running.runner_unit],
        ["systemctl", "--user", "is-active", "--quiet", running.runner_unit],
    ]
    assert store.get(attempt.attempt_id).status == "cancelled"
    assert not fifo.exists() and not result.exists()


def test_runner_command_is_exactly_allowlisted(runner_script):
    command = runner_script.hermes_command("anthropic", "Loumna", 900)
    assert command == [
        "hermes", "auth", "add", "anthropic", "--type", "oauth",
        "--label", "Loumna", "--no-browser", "--timeout", "900",
    ]
    with pytest.raises(ValueError):
        runner_script.hermes_command("openai", "Loumna", 900)
    with pytest.raises(ValueError):
        runner_script.hermes_command("anthropic", "bad;alias", 900)
    with pytest.raises(ValueError):
        runner_script.hermes_command("anthropic", "Loumna", 60)


def test_runner_redacts_output_to_authorization_fields_only(runner_script):
    output = """Open https://auth.example/authorize?client_id=public\nDevice code: ABCD-EFGH\naccess_token=private-token\nrefresh_token=private-refresh\nSuccess\n"""
    result = runner_script.redacted_result(output, returncode=0)

    assert result == {
        "status": "succeeded",
        "authorization_url": "https://auth.example/authorize?client_id=public",
        "device_code": "ABCD-EFGH",
    }
    assert "private-token" not in json.dumps(result)
    assert "private-refresh" not in json.dumps(result)


def test_runner_rejects_token_bearing_authorization_url(runner_script):
    output = "Authorization URL: https://auth.example/authorize?access_token=private-token\n"

    result = runner_script.redacted_result(output, None)

    assert result == {"status": "running"}
    assert "private-token" not in json.dumps(result)


def test_runner_parses_real_codex_multiline_ansi_prompt(runner_script):
    output = (
        "  1. Open this URL in your browser:\r\n"
        "     \x1b[94mhttps://auth.openai.com/codex/device\x1b[0m\r\n"
        "  2. Enter this code:\r\n"
        "     \x1b[94mABCD-EFGH\x1b[0m\r\n"
        "Waiting for sign-in...\r\n"
    )

    assert runner_script.redacted_result(output, None) == {
        "status": "running",
        "authorization_url": "https://auth.openai.com/codex/device",
        "device_code": "ABCD-EFGH",
    }


def test_runner_always_removes_fifo_and_raw_log(tmp_path, runner_script, monkeypatch):
    fifo = tmp_path / "input.fifo"
    state = tmp_path / "result.json"
    raw_log = state.with_suffix(".raw.log")

    class FakeProcess:
        stdout = iter(["Authorization URL: https://auth.example/device\n", "Success\n"])
        def wait(self, timeout=None):
            return 0
        def kill(self):
            pass

    captured = {}
    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        raw_log.write_text("raw private OAuth response", encoding="utf-8")
        return FakeProcess()

    monkeypatch.setattr(runner_script.subprocess, "Popen", fake_popen)
    result = runner_script.run_oauth("openai-codex", "Agentik", fifo, state, 900)

    assert result == 0
    assert captured["argv"][:2] == ["script", "-qec"]
    assert captured["argv"][-1] == str(raw_log)
    assert not fifo.exists()
    assert not raw_log.exists()
    retained = state.read_text(encoding="utf-8")
    assert "private OAuth response" not in retained
    assert json.loads(retained)["status"] == "succeeded"
    assert stat.S_IMODE(state.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "query",
    [
        "code=SECRET-CODE",
        "token=SECRET-TOKEN",
        "id_token=SECRET-ID",
        "client_secret=SECRET-CLIENT",
        "device_code=SECRET-DEVICE",
        "device-code=SECRET-DEVICE",
        "deviceCode=SECRET-DEVICE",
        "api-key=SECRET-API",
        "apiKey=SECRET-API",
        "user_password=SECRET-PASSWORD",
    ],
)
def test_runner_rejects_every_secret_bearing_authorization_url(runner_script, query):
    result = runner_script.redacted_result(
        f"Authorization URL: https://auth.example/callback?{query}\n", None
    )

    assert result == {"status": "running"}
    assert "SECRET" not in json.dumps(result)


def test_late_start_is_bounded_by_original_attempt_deadline(tmp_path, oauth):
    now = [1000.0]
    store = oauth.OAuthAttemptStore(tmp_path, clock=lambda: now[0])
    attempt = store.create("openai-codex", "add", "Agentik", None, 7)
    now[0] = attempt.expires_at - 1.0
    systemd = FakeSystemd()

    oauth.OAuthRunner(store, systemd, runner_script=RUNNER_MODULE).start(attempt.attempt_id)

    argv = systemd.calls[0]
    runtime_property = next(value for value in argv if value.startswith("RuntimeMaxSec="))
    assert float(runtime_property.removeprefix("RuntimeMaxSec=").removesuffix("s")) <= 1.0
    assert float(argv[argv.index("--deadline") + 1]) == attempt.expires_at
    assert argv[argv.index("--timeout") + 1] == "900"


def test_cancel_winning_during_start_is_not_revived(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("openai-codex", "add", "Agentik", None, 7)
    calls = []
    runner = None

    def racing_systemd(argv):
        calls.append(list(argv))
        if argv[0] == "systemd-run":
            assert runner.cancel(attempt.attempt_id) is True
            return 0
        if argv[:4] == ["systemctl", "--user", "is-active", "--quiet"]:
            return 3
        return 0

    runner = oauth.OAuthRunner(store, racing_systemd, runner_script=RUNNER_MODULE)

    with pytest.raises(ValueError, match="cancelled"):
        runner.start(attempt.attempt_id)

    assert store.get(attempt.attempt_id).status == "cancelled"
    assert any(call[:3] == ["systemctl", "--user", "stop"] for call in calls)


def test_duplicate_start_is_rejected_while_first_start_is_reserved(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("openai-codex", "add", "Agentik", None, 7)
    runner = None
    nested_errors = []

    def racing_systemd(argv):
        if argv[0] == "systemd-run":
            try:
                runner.start(attempt.attempt_id)
            except ValueError as exc:
                nested_errors.append(str(exc))
        return 0

    runner = oauth.OAuthRunner(store, racing_systemd, runner_script=RUNNER_MODULE)
    started = runner.start(attempt.attempt_id)

    assert started.status == "running"
    assert nested_errors == ["attempt is not startable"]


def test_cancel_intent_survives_stop_failure_before_unit_is_visible(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("openai-codex", "add", "Agentik", None, 7)
    calls = []
    runner_box = {}

    def racing_systemd(argv):
        calls.append(list(argv))
        if argv[0] == "systemd-run":
            assert runner_box["runner"].cancel(attempt.attempt_id) is False
            return 0
        if argv[:3] == ["systemctl", "--user", "stop"]:
            return 1 if sum(call[:3] == argv[:3] for call in calls) == 1 else 0
        if argv[:4] == ["systemctl", "--user", "is-active", "--quiet"]:
            return 3
        return 0

    runner = oauth.OAuthRunner(store, racing_systemd, runner_script=RUNNER_MODULE)
    runner_box["runner"] = runner

    with pytest.raises(ValueError, match="cancelled"):
        runner.start(attempt.attempt_id)

    assert store.get(attempt.attempt_id).status == "cancelled"


def test_runner_create_stops_and_cleans_running_conflict(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    old = store.create("openai-codex", "add", "Agentik", None, 7)
    unit = f"agk-account-oauth-{old.attempt_id}.service"
    old = store.update(old.attempt_id, status="running", runner_unit=unit)
    systemd = FakeSystemd()
    runner = oauth.OAuthRunner(store, systemd)
    for path in (runner.fifo_path(old), runner.result_path(old), runner.result_path(old).with_suffix(".raw.log")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    replacement = runner.create("openai-codex", "add", "Agentik", None, 7)

    assert store.get(old.attempt_id).status == "cancelled"
    assert replacement.status == "pending"
    assert systemd.calls[0] == ["systemctl", "--user", "stop", unit]
    assert all(not path.exists() for path in (runner.fifo_path(old), runner.result_path(old), runner.result_path(old).with_suffix(".raw.log")))


def test_cancel_fails_closed_when_systemd_stop_fails(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("anthropic", "add", "Loumna", None, 7)
    unit = f"agk-account-oauth-{attempt.attempt_id}.service"
    attempt = store.update(attempt.attempt_id, status="running", runner_unit=unit)
    result = store.path.parent / f"{attempt.attempt_id}.result.json"
    result.write_text('{"status":"running"}', encoding="utf-8")
    runner = oauth.OAuthRunner(store, lambda argv: 1)

    assert runner.cancel(attempt.attempt_id) is False
    assert store.get(attempt.attempt_id).status == "running"
    assert result.exists()


def test_cancel_fails_closed_when_inactivity_query_is_indeterminate(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("anthropic", "add", "Loumna", None, 7)
    unit = f"agk-account-oauth-{attempt.attempt_id}.service"
    attempt = store.update(attempt.attempt_id, status="running", runner_unit=unit)
    result = store.path.parent / f"{attempt.attempt_id}.result.json"
    result.write_text('{"status":"running"}', encoding="utf-8")
    calls = []

    def query_error_systemd(argv):
        calls.append(list(argv))
        if argv[:4] == ["systemctl", "--user", "is-active", "--quiet"]:
            return 1
        return 0

    runner = oauth.OAuthRunner(store, query_error_systemd)

    assert runner.cancel(attempt.attempt_id) is False
    assert store.get(attempt.attempt_id).status == "running"
    assert result.exists()
    assert not any(call[:3] == ["systemctl", "--user", "reset-failed"] for call in calls)


def test_cancel_accepts_explicit_unit_not_found_outcome(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("openai-codex", "add", "Agentik", None, 7)
    unit = f"agk-account-oauth-{attempt.attempt_id}.service"
    store.update(attempt.attempt_id, status="running", runner_unit=unit)

    def not_found_systemd(argv):
        if argv[:4] == ["systemctl", "--user", "is-active", "--quiet"]:
            return 4
        return 0

    assert oauth.OAuthRunner(store, not_found_systemd).cancel(attempt.attempt_id)
    assert store.get(attempt.attempt_id).status == "cancelled"


def test_cancel_during_failed_start_terminalizes_and_cleans_attempt(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("openai-codex", "add", "Agentik", None, 7)
    runner_box = {}

    def failed_start_systemd(argv):
        if argv[0] == "systemd-run":
            runner = runner_box["runner"]
            for path in (
                runner.fifo_path(attempt),
                runner.result_path(attempt),
                runner.result_path(attempt).with_suffix(".raw.log"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            assert runner.cancel(attempt.attempt_id) is False
            return 1
        if argv[:3] == ["systemctl", "--user", "stop"]:
            return 1
        return 0

    runner = oauth.OAuthRunner(store, failed_start_systemd, runner_script=RUNNER_MODULE)
    runner_box["runner"] = runner

    with pytest.raises(RuntimeError, match="failed to start"):
        runner.start(attempt.attempt_id)

    stored = store.get(attempt.attempt_id)
    assert stored.status == "cancelled"
    assert stored.runner_unit == ""
    assert all(
        not path.exists()
        for path in (
            runner.fifo_path(stored),
            runner.result_path(stored),
            runner.result_path(stored).with_suffix(".raw.log"),
        )
    )


def test_get_reconciles_terminal_runner_result_into_durable_store(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("openai-codex", "add", "Agentik", None, 7)
    store.update(attempt.attempt_id, status="running")
    result = store.path.parent / f"{attempt.attempt_id}.result.json"
    result.write_text('{"status":"succeeded","authorization_url":"https://auth.example/device"}', encoding="utf-8")

    assert store.get(attempt.attempt_id).status == "succeeded"
    persisted = json.loads(store.path.read_text(encoding="utf-8"))["attempts"]
    assert next(row for row in persisted if row["attempt_id"] == attempt.attempt_id)["status"] == "succeeded"


def test_get_durably_expires_stale_live_attempt(tmp_path, oauth):
    now = [1000.0]
    store = oauth.OAuthAttemptStore(tmp_path, clock=lambda: now[0])
    attempt = store.create("openai-codex", "add", "Agentik", None, 7)
    now[0] = attempt.expires_at

    assert store.get(attempt.attempt_id).status == "expired"
    assert '"status": "expired"' in store.path.read_text(encoding="utf-8")


def test_store_rejects_backward_live_status_transition(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("openai-codex", "add", "Agentik", None, 7)
    store.update(attempt.attempt_id, status="running")

    with pytest.raises(ValueError, match="invalid attempt status transition"):
        store.update(attempt.attempt_id, status="pending")

    assert store.get(attempt.attempt_id).status == "running"


def test_partial_fifo_write_is_not_marked_submitted(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("anthropic", "add", "Loumna", None, 7, channel_id=44)
    runner = oauth.OAuthRunner(store, FakeSystemd(), fifo_writer=lambda _path, _value: 2)

    assert runner.submit_claude_code(attempt.attempt_id, "code#state", user_id=7, channel_id=44) is False
    assert store.get(attempt.attempt_id).status != "code-submitted"


def test_cancel_winning_during_fifo_write_is_not_revived(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("anthropic", "add", "Loumna", None, 7, channel_id=44)
    runner = None

    def racing_writer(_path, value):
        assert runner.cancel(attempt.attempt_id) is True
        return len(value.encode("utf-8"))

    runner = oauth.OAuthRunner(store, FakeSystemd(), fifo_writer=racing_writer)

    assert runner.submit_claude_code(attempt.attempt_id, "code#state", user_id=7, channel_id=44) is False
    assert store.get(attempt.attempt_id).status == "cancelled"


def test_duplicate_submission_is_rejected_while_first_write_is_reserved(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("anthropic", "add", "Loumna", None, 7, channel_id=44)
    runner_box = {}
    nested_results = []

    def racing_writer(_path, value):
        nested_results.append(
            runner_box["runner"].submit_claude_code(
                attempt.attempt_id, "other#state", user_id=7, channel_id=44
            )
        )
        return len(value.encode("utf-8"))

    runner = oauth.OAuthRunner(store, FakeSystemd(), fifo_writer=racing_writer)
    runner_box["runner"] = runner

    assert runner.submit_claude_code(
        attempt.attempt_id, "code#state", user_id=7, channel_id=44
    ) is True
    assert nested_results == [False]
    assert store.get(attempt.attempt_id).status == "code-submitted"


def test_cancel_fails_closed_when_unit_remains_active(tmp_path, oauth):
    store = oauth.OAuthAttemptStore(tmp_path)
    attempt = store.create("openai-codex", "add", "Agentik", None, 7)
    unit = f"agk-account-oauth-{attempt.attempt_id}.service"
    store.update(attempt.attempt_id, status="running", runner_unit=unit)
    runner = oauth.OAuthRunner(store, lambda _argv: 0)

    assert runner.cancel(attempt.attempt_id) is False
    assert store.get(attempt.attempt_id).status == "running"


def test_runner_wait_uses_absolute_deadline(tmp_path, runner_script, monkeypatch):
    fifo = tmp_path / "input.fifo"
    state = tmp_path / "result.json"
    observed = {}

    class FakeProcess:
        stdout = iter(())

        def wait(self, timeout=None):
            observed["timeout"] = timeout
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(runner_script.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())
    monkeypatch.setattr(runner_script.time, "time", lambda: 1000.0)

    assert runner_script.run_oauth(
        "openai-codex", "Agentik", fifo, state, 900, deadline=1001.25
    ) == 0
    assert observed["timeout"] == pytest.approx(1.25)
