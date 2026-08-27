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
    runner = oauth.OAuthRunner(store, FakeSystemd(), fifo_writer=lambda path, value: writes.append((path, value)))

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
    assert systemd.calls == [["systemctl", "--user", "stop", running.runner_unit]]
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
