import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


MODULE = Path(__file__).resolve().parents[1] / "hermes/plugins/platforms/discord/agk_session_control.py"
spec = importlib.util.spec_from_file_location("agk_session_control", MODULE)
assert spec and spec.loader
control = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = control
spec.loader.exec_module(control)


def make_runtime_db(path: Path):
    with sqlite3.connect(path) as db:
        db.execute(
            """CREATE TABLE runtime_sessions (
            id TEXT PRIMARY KEY, name TEXT, type TEXT, environment TEXT,
            rmux_session TEXT, cwd TEXT, status TEXT, last_activity REAL,
            archived_at REAL, hermes_session TEXT)"""
        )
        db.execute(
            "INSERT INTO runtime_sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("RT-ABC123", "builder", "hermes", "operator", "builder", "/home/operator", "working", 10.0, None, "S-1"),
        )


def make_hermes_db(path: Path):
    with sqlite3.connect(path) as db:
        db.execute(
            """CREATE TABLE sessions (
            id TEXT PRIMARY KEY, title TEXT, source TEXT, message_count INTEGER,
            last_activity_at REAL, started_at REAL, archived INTEGER, cwd TEXT,
            profile_name TEXT)"""
        )
        db.execute(
            """CREATE TABLE messages (
            id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,
            tool_name TEXT, timestamp REAL, active INTEGER)"""
        )
        db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?)",
            ("S-1", "Build control center", "cli", 4, 12.0, 1.0, 0, "/home/operator", None),
        )
        todo = {"todos": [
            {"id": "a", "content": "Design", "status": "completed"},
            {"id": "b", "content": "Build", "status": "in_progress"},
            {"id": "c", "content": "Verify", "status": "pending"},
        ]}
        db.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?)",
            (1, "S-1", "tool", json.dumps(todo), "todo", 11.0, 1),
        )


def test_progress_bar_counts_completed_cancelled_and_total():
    progress = control.plan_progress([
        {"status": "completed"}, {"status": "cancelled"},
        {"status": "in_progress"}, {"status": "pending"},
    ])
    assert progress.completed == 2
    assert progress.total == 4
    assert progress.percent == 50
    assert progress.bar == "█████░░░░░"


def test_catalog_merges_runtime_and_hermes_session_without_duplicate(tmp_path):
    runtime = tmp_path / "runtime.db"
    hermes = tmp_path / "state.db"
    make_runtime_db(runtime)
    make_hermes_db(hermes)
    rows = control.catalog_for_environment("operator", runtime, [("default", hermes)])
    assert len(rows) == 1
    assert rows[0].runtime_id == "RT-ABC123"
    assert rows[0].hermes_session_id == "S-1"
    assert rows[0].progress.percent == 33
    assert rows[0].can_prompt is True
    assert rows[0].can_stop is True


def test_target_parser_rejects_unknown_environment_and_malformed_ids():
    with pytest.raises(control.ControlError):
        control.parse_target("runtime:root:RT-ABC123")
    with pytest.raises(control.ControlError):
        control.parse_target("runtime:operator:../../etc/passwd")


def test_destructive_actions_require_confirmation_token():
    target = control.parse_target("runtime:operator:RT-ABC123")
    with pytest.raises(control.ControlError, match="confirmation"):
        control.require_confirmation(target, "wrong")
    token = control.confirmation_token(target)
    control.require_confirmation(target, token)


def test_channel_guard_accepts_only_configured_manager_channel():
    assert control.channel_allowed(1542462952714670190)
    assert not control.channel_allowed(1541820137148260432)


def test_log_redaction_removes_secret_like_values():
    text = "OPENROUTER_API_KEY=sk-or-v1-secret Authorization: Bearer abcdefghijklmnop"
    redacted = control.redact_log(text)
    assert "sk-or" not in redacted
    assert "abcdefghijklmnop" not in redacted
    assert "[REDACTED]" in redacted


def test_log_redaction_happens_before_boundary_truncation():
    value = "x" * 20000
    redacted = control.redact_log("API_KEY=" + value, limit=32)
    assert "x" not in redacted


def test_runtime_action_argv_is_fixed_and_uses_resolved_session_name(tmp_path):
    runtime = tmp_path / "runtime.db"
    make_runtime_db(runtime)
    controller = control.StationSessionController(
        environments={"operator": control.EnvironmentPaths("operator", tmp_path, runtime, [])}
    )
    target = control.parse_target("runtime:operator:RT-ABC123")
    assert controller.runtime_action_argv(target, "stop") == [
        "/usr/local/bin/agk", "kill", "builder", "--yes"
    ]
    assert controller.runtime_action_argv(target, "archive") == [
        "/usr/local/bin/agk", "close", "builder", "--yes"
    ]
    assert controller.runtime_action_argv(target, "delete") == [
        "/usr/local/bin/agk", "purge", "builder", "--yes"
    ]


def test_prompt_rejects_non_runtime_target_and_oversized_text(tmp_path):
    controller = control.StationSessionController(environments={})
    with pytest.raises(control.ControlError, match="live AGK runtime"):
        controller.validate_prompt(control.parse_target("hermes:operator:S-1"), "hello")
    with pytest.raises(control.ControlError, match="1-4000"):
        controller.validate_prompt(control.parse_target("runtime:operator:RT-ABC123"), "x" * 4001)


def test_hermes_archive_updates_only_exact_session(tmp_path):
    state = tmp_path / "state.db"
    make_hermes_db(state)
    controller = control.StationSessionController(
        environments={"operator": control.EnvironmentPaths("operator", tmp_path, tmp_path / "none.db", [("default", state)])}
    )
    target = control.parse_target("hermes:operator:S-1")
    controller.archive_hermes(target)
    with sqlite3.connect(state) as db:
        assert db.execute("SELECT archived FROM sessions WHERE id='S-1'").fetchone()[0] == 1


def test_progress_label_renders_plan_state():
    progress = control.PlanProgress(3, 5, 60, "██████░░░░")
    assert control.progress_label(progress) == "██████░░░░ 60% · 3/5"


def test_send_prompt_uses_literal_rmux_keys_under_environment_owner(tmp_path):
    runtime = tmp_path / "runtime.db"
    make_runtime_db(runtime)
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        if "list-panes" in argv:
            return subprocess.CompletedProcess(argv, 0, "%7\n", "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    controller = control.StationSessionController(
        environments={"operator": control.EnvironmentPaths("operator", tmp_path, runtime, [])},
        runner=fake_runner,
    )
    controller.send_prompt(control.parse_target("runtime:operator:RT-ABC123"), "Build it now")
    assert any(argv[-2:] == ["-l", "Build it now"] for argv in calls)
    assert any("=builder" in argv for argv in calls if "list-panes" in argv)
    assert all("operator" in argv for argv in calls)


def test_runtime_delete_requires_matching_confirmation(tmp_path):
    runtime = tmp_path / "runtime.db"
    make_runtime_db(runtime)
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "purged", "")

    controller = control.StationSessionController(
        environments={"operator": control.EnvironmentPaths("operator", tmp_path, runtime, [])},
        runner=fake_runner,
    )
    target = control.parse_target("runtime:operator:RT-ABC123")
    with pytest.raises(control.ControlError, match="confirmation"):
        controller.apply_runtime_action(target, "delete", confirmation="")
    result = controller.apply_runtime_action(target, "delete", confirmation=control.confirmation_token(target))
    assert result == "purged"
    assert calls[-1][-3:] == ["purge", "builder", "--yes"]


def test_runtime_logs_are_redacted_and_bounded(tmp_path):
    runtime = tmp_path / "runtime.db"
    make_runtime_db(runtime)

    def fake_runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "OPENROUTER_API_KEY=sk-or-v1-secret\nlast line", "")

    controller = control.StationSessionController(
        environments={"operator": control.EnvironmentPaths("operator", tmp_path, runtime, [])},
        runner=fake_runner,
    )
    logs = controller.logs(control.parse_target("runtime:operator:RT-ABC123"))
    assert "sk-or" not in logs
    assert "last line" in logs


def test_complete_runtime_disables_prompt_and_stop():
    record = control.SessionRecord("operator", "done", "complete", runtime_id="RT-DONE", rmux_session="done")
    assert record.can_prompt is False
    assert record.can_stop is False


def test_archive_uses_single_close_transition(tmp_path):
    runtime = tmp_path / "runtime.db"
    make_runtime_db(runtime)
    calls = []
    def fake_runner(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    controller = control.StationSessionController(
        environments={"operator": control.EnvironmentPaths("operator", tmp_path, runtime, [])}, runner=fake_runner
    )
    target = control.parse_target("runtime:operator:RT-ABC123")
    controller.apply_runtime_action(target, "archive", control.confirmation_token(target))
    joined = [" ".join(argv) for argv in calls]
    transitions = [command for command in joined if "/usr/local/bin/agk" in command]
    assert len(transitions) == 1
    assert " close builder --yes" in transitions[0]


def test_cross_profile_prompt_uses_stdin_not_process_arguments(tmp_path, monkeypatch):
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "prompt delivered", "")

    paths = control.EnvironmentPaths("mission", tmp_path, tmp_path / "runtime.db", [])
    controller = control.StationSessionController(environments={"mission": paths}, runner=fake_runner)
    monkeypatch.setattr(controller, "_local_to", lambda _paths: False)
    target = control.parse_target("runtime:mission:RT-ABC123")
    controller.send_prompt(target, "private mission prompt")
    argv, kwargs = calls[-1]
    assert "private mission prompt" not in argv
    assert kwargs["input"] == "private mission prompt"


def test_catalog_falls_back_to_owner_scoped_helper_for_isolated_home(tmp_path):
    calls = []
    payload = [{
        "environment": "agentik", "display_name": "remote-agent", "status": "idle",
        "runtime_type": "hermes", "runtime_id": "RT-REMOTE", "runtime_name": "remote-agent",
        "rmux_session": "remote-agent", "hermes_session_id": None, "profile": "default",
        "title": "", "cwd": "/home/agentik", "last_activity": 5.0,
        "progress": {"completed": 1, "total": 2, "percent": 50, "bar": "█████░░░░░"},
    }]

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

    paths = control.EnvironmentPaths("agentik", Path("/home/agentik"), tmp_path / "missing.db", [])
    rows = control.StationSessionController(environments={"agentik": paths}, runner=fake_runner).list_sessions()
    assert rows[0].display_name == "remote-agent"
    assert rows[0].progress.percent == 50
    assert any("catalog" in argv for argv in calls)
