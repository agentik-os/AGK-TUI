from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "agk_control.py"
SPEC = importlib.util.spec_from_file_location("agk_control_tested", MODULE_PATH)
assert SPEC and SPEC.loader
agk = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agk
SPEC.loader.exec_module(agk)


def completed(stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def test_session_types_and_filter_language():
    assert {"hermes", "claude", "codex", "opencode", "openrouter"} <= agk.TYPES
    rows = [{"type": "hermes", "environment": "mission", "client": "moonbase",
             "project": "growth", "status": "running", "name": "mission-moonbase-growth"}]
    assert agk.filtered(rows, "type:hermes env:mission client:moonbase") == rows
    assert agk.filtered(rows, "status:failed") == []


def test_create_persists_runtime_metadata_and_rmux_marker(tmp_path, monkeypatch):
    calls = []
    def fake_run(*args, check=True):
        calls.append(args)
        return completed(returncode=1 if args[1:3] == ("has-session", "-t") else 0)
    monkeypatch.setattr(agk, "run", fake_run)
    env = agk.Environment("agentik", tmp_path, tmp_path / "workspace" / "projects")
    registry = agk.RuntimeRegistry(env)
    row = registry.create(name="agentik-hermes-dev", kind="hermes", cwd=tmp_path,
                          project="PRJ-1", native_session="S-1",
                          command=["hermes", "--resume", "S-1"])
    assert row["type"] == "hermes"
    assert row["native_session"] == "S-1"
    assert row["project"] == "PRJ-1"
    create_call = next(call for call in calls if call[1] == "new-session")
    assert "AGENTIK_RMUX=1" in create_call
    assert "AGENTIK_ENVIRONMENT=agentik" in create_call
    assert any(value.startswith("PATH=") for value in create_call)


def test_create_rejects_cwd_outside_linux_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(agk, "run", lambda *args, **kwargs: completed(returncode=1))
    registry = agk.RuntimeRegistry(agk.Environment("private", tmp_path / "private", tmp_path / "private" / "projects"))
    registry.env.home.mkdir(parents=True, exist_ok=True)
    try:
        registry.create(name="private-invalid-work", kind="shell", cwd=tmp_path / "mission")
    except ValueError as exc:
        assert "trust boundary" in str(exc)
    else:
        raise AssertionError("cross-environment cwd was accepted")


def test_reconcile_marks_missing_runtime_interrupted(tmp_path, monkeypatch):
    monkeypatch.setattr(agk, "run", lambda *args, **kwargs: completed(returncode=1))
    registry = agk.RuntimeRegistry(agk.Environment("operator", tmp_path, tmp_path))
    now = 1.0
    registry.db.execute("""
      INSERT INTO runtime_sessions(
        id,name,type,environment,rmux_session,cwd,status,created_at,last_activity,
        native_session,command_json
      ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, ("RT-1", "operator-maintenance", "shell", "operator",
           "operator-maintenance", str(tmp_path), "running", now, now, None, "[]"))
    registry.db.commit()
    changed, unmanaged = registry.reconcile()
    assert changed == 1 and unmanaged == []
    assert registry.get("RT-1")["status"] == "interrupted"


def test_default_resume_commands_use_documented_cli(monkeypatch):
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/verified/{name}")
    assert agk.default_command("hermes", "S-1") == ["/verified/hermes", "--resume", "S-1"]
    assert agk.default_command("hermes", "S-2", "research") == [
        "/verified/hermes", "--profile", "research", "--resume", "S-2"
    ]
    assert agk.default_command("claude", "C-1") == [
        "/verified/env", "CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN=1",
        "/verified/claude", "--dangerously-skip-permissions", "--resume", "C-1"
    ]
    assert agk.default_command("codex", "X-1") == ["/verified/codex", "resume", "X-1"]


def test_openrouter_sessions_pin_the_supported_model(monkeypatch):
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/verified/{name}")
    monkeypatch.delenv("AGK_OPENROUTER_MODEL", raising=False)
    assert agk.default_command("openrouter") == [
        "/verified/hermes", "--provider", "openrouter", "--model", "stealth/ox-alpha"
    ]


def test_specialist_start_binds_catalog_profile_and_durable_rmux(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog"
    definition = catalog / "kitchen-agent"
    definition.mkdir(parents=True)
    (definition / "agent.yaml").write_text(
        "id: kitchen-agent\n"
        "name: Kitchen Agent\n"
        "version: 1.2.3\n"
        "scope: [mission]\n"
        "profile: kitchen\n"
        "os: [kitchen-os@1.0.0]\n"
        "prompt: prompt.md\n",
        encoding="utf-8",
    )
    (definition / "prompt.md").write_text("Run the kitchen OS.\n", encoding="utf-8")
    (tmp_path / ".hermes/profiles/kitchen").mkdir(parents=True)
    monkeypatch.setenv("AGK_AGENT_CATALOG", str(catalog))
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/verified/{name}")

    class Runtime:
        def __init__(self):
            self.created = []

        def has_session(self, _name):
            return False

        def create(self, name, kind, cwd, environment, command):
            self.created.append((name, kind, cwd, environment, command))

    runtime = Runtime()
    env = agk.Environment("mission", tmp_path, tmp_path / "workspace/clients")
    registry = agk.RuntimeRegistry(env, runtime=runtime)

    row, created = agk.start_specialist(env, registry, "kitchen-agent")

    workspace = tmp_path / ".agentik/agents/kitchen-agent/workspace"
    assert created is True
    assert row["name"] == "mission-kitchen-agent"
    assert row["hermes_profile"] == "kitchen"
    assert agk.json.loads(row["command_json"]) == [
        "/verified/hermes", "-p", "kitchen", "--in", str(workspace)
    ]
    assert runtime.created[0][0] == "mission-kitchen-agent"
    assert (workspace / "AGENTS.md").read_text(encoding="utf-8") == "Run the kitchen OS.\n"
    assert agk.json.loads(
        (workspace / ".agentik-agent.json").read_text(encoding="utf-8")
    )["os"] == ["kitchen-os@1.0.0"]


def test_specialist_scope_is_enforced_outside_operator(tmp_path, monkeypatch):
    definition = tmp_path / "catalog/operator-agent"
    definition.mkdir(parents=True)
    (definition / "agent.yaml").write_text(
        "id: operator-agent\nscope: [operator]\nprompt: prompt.md\n",
        encoding="utf-8",
    )
    (definition / "prompt.md").write_text("Operate.\n", encoding="utf-8")
    monkeypatch.setenv("AGK_AGENT_CATALOG", str(tmp_path / "catalog"))
    env = agk.Environment("private", tmp_path, tmp_path / "workspace/projects")

    try:
        agk.specialist_definition(env, "operator-agent")
    except PermissionError as error:
        assert "not allowed in private" in str(error)
    else:
        raise AssertionError("cross-profile specialist launch was accepted")


def test_claude_workspace_trust_is_persisted_without_losing_existing_state(tmp_path):
    config = tmp_path / ".claude.json"
    config.write_text(
        '{"theme":"dark","projects":{"/existing":{"custom":true}}}\n',
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    agk.trust_claude_workspace(tmp_path, workspace)

    document = agk.json.loads(config.read_text(encoding="utf-8"))
    assert document["theme"] == "dark"
    assert document["projects"]["/existing"] == {"custom": True}
    assert document["projects"][str(workspace)]["hasTrustDialogAccepted"] is True
    assert config.stat().st_mode & 0o777 == 0o600


def test_kill_yes_uses_the_confirmed_noninteractive_path(monkeypatch):
    row = {"name": "agk-test-session"}

    class Registry:
        def __init__(self):
            self.terminated = []

        def reconcile(self):
            return 0, []

        def get(self, target):
            return row if target == row["name"] else None

        def terminate(self, target):
            self.terminated.append(target)
            return target

    registry = Registry()
    monkeypatch.setattr(
        agk.Environment,
        "current",
        lambda: agk.Environment("operator", Path("/tmp"), Path("/tmp")),
    )
    monkeypatch.setattr(agk, "RuntimeRegistry", lambda _env: registry)
    monkeypatch.setattr(sys, "argv", ["agk", "kill", "--yes", row["name"]])

    assert agk.main() == 0
    assert registry.terminated == [row]


def test_close_yes_terminates_then_archives_without_a_second_prompt(monkeypatch):
    row = {"name": "agk-close-session"}

    class Registry:
        def __init__(self):
            self.actions = []

        def reconcile(self):
            return 0, []

        def get(self, target):
            return row if target == row["name"] else None

        def terminate(self, target):
            self.actions.append(("terminate", target))
            return target

        def archive(self, target):
            self.actions.append(("archive", target))
            return target

    registry = Registry()
    monkeypatch.setattr(
        agk.Environment,
        "current",
        lambda: agk.Environment("operator", Path("/tmp"), Path("/tmp")),
    )
    monkeypatch.setattr(agk, "RuntimeRegistry", lambda _env: registry)
    monkeypatch.setattr(sys, "argv", ["agk", "close", "--yes", row["name"]])

    assert agk.main() == 0
    assert registry.actions == [("terminate", row), ("archive", row)]


def test_rmux_terminate_retries_and_fails_if_session_survives(monkeypatch):
    calls = []

    def fake_run(*args, check=True):
        calls.append(args)
        if args[1] == "has-session":
            return completed(returncode=0)
        return completed(stdout="still busy", returncode=1)

    monkeypatch.setattr(agk, "run", fake_run)
    try:
        agk.RmuxRuntime().terminate("agk-stuck-session")
    except RuntimeError as exc:
        assert "still alive" in str(exc)
    else:
        raise AssertionError("a surviving RMUX session was reported as closed")
    assert sum(call[1] == "kill-session" for call in calls) == 2


def test_purge_yes_removes_the_exact_runtime_without_prompt(monkeypatch):
    row = {"name": "agk-obsolete-session"}

    class Registry:
        def __init__(self):
            self.purged = []

        def reconcile(self):
            return 0, []

        def get(self, target):
            return row if target == row["name"] else None

        def purge(self, target):
            self.purged.append(target)
            return target["name"]

    registry = Registry()
    monkeypatch.setattr(
        agk.Environment,
        "current",
        lambda: agk.Environment("operator", Path("/tmp"), Path("/tmp")),
    )
    monkeypatch.setattr(agk, "RuntimeRegistry", lambda _env: registry)
    monkeypatch.setattr(sys, "argv", ["agk", "purge", "--yes", row["name"]])

    assert agk.main() == 0
    assert registry.purged == [row]


def test_responsive_layout_and_navigation_model():
    assert agk.layout_mode(60, 30) == "compact"
    assert agk.layout_mode(90, 24) == "standard"
    assert agk.layout_mode(140, 40) == "wide"
    left, right = agk.pane_widths(140, "wide")
    assert left >= 38 and right > left
    assert agk.pane_widths(80, "standard") == (80, 0)
    assert agk.cycle_view("sessions") == "projects"
    assert agk.cycle_view("sessions", reverse=True) == "settings"


def test_public_single_user_environment_config(tmp_path, monkeypatch):
    config = tmp_path / ".config/agk/environment.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        f"environment: mission\nprojects_root: {tmp_path}/work/clients\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("USER", "public-user")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGK_ENV_CONFIG", str(config))
    env = agk.Environment.current()
    assert env.name == "mission"
    assert env.home == tmp_path
    assert env.projects == tmp_path / "work/clients"


def test_public_environment_rejects_unknown_scope(tmp_path, monkeypatch):
    config = tmp_path / "environment.yaml"
    config.write_text("environment: super-root\n", encoding="utf-8")
    monkeypatch.setenv("USER", "public-user")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGK_ENV_CONFIG", str(config))
    try:
        agk.Environment.current()
    except SystemExit as exc:
        assert "Unsupported AGK environment" in str(exc)
    else:
        raise AssertionError("unknown public environment was accepted")


def test_os_registry_prefers_explicit_path(tmp_path, monkeypatch):
    target = tmp_path / "registry"
    monkeypatch.setenv("AGK_OS_REGISTRY", str(target))
    assert agk.os_registry_path() == target


def test_session_sections_prioritize_attention_then_active_then_recent():
    rows = [
        {"status": "idle", "name": "recent"},
        {"status": "working", "name": "active"},
        {"status": "failed", "name": "failed"},
    ]
    sections = agk.session_sections(rows)
    assert [name for name, _ in sections] == ["ATTENTION", "ACTIVE", "RECENT"]
    assert [values[0]["name"] for _, values in sections] == ["failed", "active", "recent"]


def test_age_format_is_compact_and_stable():
    assert agk.format_age(990, now=1000) == "10s"
    assert agk.format_age(700, now=1000) == "5m"
    assert agk.format_age(1000 - 7200, now=1000) == "2h"


def test_mcp_inventory_is_redacted(tmp_path, monkeypatch):
    monkeypatch.setattr(agk.shutil, "which", lambda _name: None)
    env = agk.Environment("mission", tmp_path, tmp_path / "workspace/clients")
    (tmp_path / ".hermes").mkdir()
    (tmp_path / ".hermes/config.yaml").write_text(
        "mcp_servers:\n  github:\n    command: secret-command\n    env:\n      TOKEN: secret\n  browser:\n    url: https://example.invalid\n",
        encoding="utf-8",
    )
    assert agk.mcp_inventory(env) == [
        {"name": "browser", "transport": "http", "status": "configured", "toolkits": []},
        {"name": "github", "transport": "stdio", "status": "configured", "toolkits": []},
    ]
    assert "secret" not in repr(agk.mcp_inventory(env))


def test_mcp_inventory_includes_composio_connection_without_credentials(tmp_path, monkeypatch):
    env = agk.Environment("operator", tmp_path, tmp_path / "workspace")
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/usr/bin/{name}")
    auth = tmp_path / ".composio/user_data.json"
    auth.parent.mkdir()
    auth.write_text('{"api_key":"test-key","token":"never-read"}', encoding="utf-8")
    inventory = tmp_path / ".agentik/composio-connections.json"
    inventory.parent.mkdir()
    inventory.write_text(
        '{"schema_version":1,"toolkits":['
        '{"name":"github","status":"active","connections":1}]}',
        encoding="utf-8",
    )
    assert agk.mcp_inventory(env) == [{
        "name": "Composio",
        "transport": "CLI · link/tools list",
        "status": "connected",
        "toolkits": [{"name": "github", "status": "active", "connections": 1}],
    }]
    assert "never-read" not in repr(agk.mcp_inventory(env))


def test_mcp_inventory_rejects_composio_placeholder_auth(tmp_path, monkeypatch):
    env = agk.Environment("mission", tmp_path, tmp_path / "workspace")
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/usr/bin/{name}")
    auth = tmp_path / ".composio/user_data.json"
    auth.parent.mkdir()
    auth.write_text('{"api_key":null,"org_id":null}', encoding="utf-8")
    assert agk.mcp_inventory(env) == [{
        "name": "Composio",
        "transport": "CLI · link/tools list",
        "status": "setup-required",
        "toolkits": [],
    }]


def test_refresh_mcp_inventory_uses_current_profile_and_flattens_toolkits(tmp_path, monkeypatch):
    env = agk.Environment("mission", tmp_path, tmp_path / "workspace/clients")
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/usr/bin/{name}")
    auth = tmp_path / ".composio/user_data.json"
    auth.parent.mkdir()
    auth.write_text('{"api_key":"test-key"}', encoding="utf-8")
    cache = tmp_path / ".agentik/composio-connections.json"
    cache.parent.mkdir()
    cache.write_text(
        '{"schema_version":1,"toolkits":['
        '{"name":"gmail","status":"active","connections":1}]}',
        encoding="utf-8",
    )
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return completed(stdout='{"authenticated":true}')

    monkeypatch.setattr(agk.subprocess, "run", fake_run)

    items = agk.refresh_mcp_inventory(env)

    assert calls[0][0][-2:] == ["refresh", "--json"]
    assert calls[0][1]["env"]["HOME"] == str(tmp_path)
    assert calls[0][1]["env"]["USER"] == "mission"
    assert agk.mcp_display_rows(items) == [
        {
            "name": "Composio",
            "transport": "CLI · link/tools list",
            "status": "connected",
            "toolkits": [{"name": "gmail", "status": "active", "connections": 1}],
        },
        {
            "name": "Composio / gmail",
            "transport": "connected toolkit",
            "status": "active",
            "toolkits": [],
        },
    ]


def test_refresh_mcp_inventory_redacts_subprocess_failure(tmp_path, monkeypatch):
    env = agk.Environment("operator", tmp_path, tmp_path / "workspace")
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        agk.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=9, stdout="", stderr="api_key=never-expose"
        ),
    )

    try:
        agk.refresh_mcp_inventory(env)
    except RuntimeError as error:
        assert str(error) == "Composio inventory refresh failed with exit code 9"
        assert "never-expose" not in str(error)
    else:
        raise AssertionError("a failed inventory refresh was accepted")


def test_mcp_inventory_surfaces_invalid_hermes_config_in_strict_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(agk.shutil, "which", lambda _name: None)
    env = agk.Environment("private", tmp_path, tmp_path / "workspace/projects")
    config = tmp_path / ".hermes/config.yaml"
    config.parent.mkdir()
    config.write_text("mcp_servers: [not, an, object]\n", encoding="utf-8")

    try:
        agk.mcp_inventory(env, strict=True)
    except RuntimeError as error:
        assert "mcp_servers must be an object" in str(error)
    else:
        raise AssertionError("an invalid Hermes MCP config was accepted")


def test_skill_inventory_reports_identity_and_source_only(tmp_path):
    env = agk.Environment("private", tmp_path, tmp_path / "workspace/projects")
    skill = tmp_path / ".hermes/skills/research"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("private instructions", encoding="utf-8")
    assert agk.skill_inventory(env) == [
        {"name": "research", "source": "hermes", "status": "installed"},
    ]


def test_rmux_adapter_uses_stable_pane_id_for_respawn(monkeypatch):
    calls = []
    def fake_run(*args, check=True):
        calls.append(args)
        if args[1] == "list-panes":
            return completed("%42\n")
        return completed()
    monkeypatch.setattr(agk, "run", fake_run)
    runtime = agk.RmuxRuntime()
    runtime.respawn("mission-moonbase", "/home/mission/workspace", ["hermes", "--resume", "S-1"])
    command = calls[-1]
    assert command[1:5] == ("respawn-pane", "-k", "-t", "%42")
    assert ":1.1" not in command
    runtime.send_input("mission-moonbase", "continue safely")
    assert calls[-2][1:] == ("send-keys", "-t", "%42", "-l", "continue safely")
    assert calls[-1][1:] == ("send-keys", "-t", "%42", "Enter")


def _registry(tmp_path, monkeypatch, live=frozenset()):
    calls = []

    def fake_run(*args, check=True):
        calls.append(args)
        if args[1:3] == ("has-session", "-t"):
            return completed(returncode=0 if args[3] in live else 1)
        return completed()

    monkeypatch.setattr(agk, "run", fake_run)
    env = agk.Environment("agentik", tmp_path, tmp_path / "workspace" / "projects")
    return agk.RuntimeRegistry(env), calls


def test_claude_sessions_own_a_conversation_id_and_restart_resumes_it(tmp_path, monkeypatch):
    registry, calls = _registry(tmp_path, monkeypatch)
    command, native = agk.launch_command("claude")
    assert command[-2:] == ["--session-id", native]
    assert agk.uuid.UUID(native).version == 4
    row = registry.create(
        name="agentik-claude-dev", kind="claude", cwd=tmp_path,
        command=command, native_session=native,
    )
    assert row["native_session"] == native

    # Before the first saved turn the id is recreated, never resumed.
    assert agk.resumable_command(tmp_path, row)[-2:] == ["--session-id", native]

    transcript = tmp_path / ".claude/projects/-work" / f"{native}.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("{}\n", encoding="utf-8")
    resumed = agk.resumable_command(tmp_path, row)
    assert resumed[-2:] == ["--resume", native]
    assert "--session-id" not in resumed
    assert resumed[: len(command) - 2] == command[:-2]

    registry.restart_frontend(row)
    create = [call for call in calls if call[1] == "new-session"][-1]
    assert create[-2:] == ("--resume", native)


def test_explicit_native_sessions_and_other_providers_keep_their_launch(tmp_path, monkeypatch):
    command, native = agk.launch_command("claude", "11111111-1111-4111-8111-111111111111")
    assert native == "11111111-1111-4111-8111-111111111111"
    assert command[-2:] == ["--resume", native]
    for kind in ("hermes", "codex", "opencode", "shell"):
        command, native = agk.launch_command(kind)
        assert native is None and "--session-id" not in command


def test_hermes_terminals_are_linked_to_their_conversation_and_resume_it(tmp_path, monkeypatch):
    registry, calls = _registry(tmp_path, monkeypatch)
    row = registry.create(
        name="agentik-hermes-main", kind="hermes", cwd=tmp_path, command=["hermes"],
    )
    other = registry.create(
        name="agentik-hermes-other", kind="hermes", cwd=tmp_path / "elsewhere"
        if (tmp_path / "elsewhere").mkdir() is None else tmp_path, command=["hermes"],
    )
    state = tmp_path / ".hermes/state.db"
    state.parent.mkdir()
    store = agk.sqlite3.connect(state)
    store.execute("CREATE TABLE sessions (id TEXT, cwd TEXT, started_at REAL, billing_provider TEXT)")
    store.executemany(
        "INSERT INTO sessions VALUES (?,?,?,?)",
        [
            ("S-MAIN", str(tmp_path.resolve()), row["created_at"] + 3, "nous"),
            ("S-OLD", str(tmp_path.resolve()), row["created_at"] - 900, "nous"),
            ("S-FAR", "/somewhere/else", row["created_at"] + 1, "nous"),
        ],
    )
    store.commit()
    store.close()

    assert registry.link_hermes_sessions() == 1
    linked = registry.get(row["id"])
    assert linked["native_session"] == "S-MAIN"
    assert linked["hermes_session"] == "S-MAIN"
    assert registry.get(other["id"])["native_session"] is None
    # Idempotent, and a linked conversation is never handed to a second terminal.
    assert registry.link_hermes_sessions() == 0

    assert agk.resumable_command(tmp_path, linked) == ["hermes", "--resume", "S-MAIN"]
    registry.restart_frontend(linked)
    create = [call for call in calls if call[1] == "new-session"][-1]
    assert create[-3:] == ("hermes", "--resume", "S-MAIN")


def test_ambiguous_hermes_matches_stay_unlinked(tmp_path, monkeypatch):
    registry, _ = _registry(tmp_path, monkeypatch)
    row = registry.create(
        name="agentik-hermes-twin", kind="hermes", cwd=tmp_path, command=["hermes"],
    )
    state = tmp_path / ".hermes/state.db"
    state.parent.mkdir()
    store = agk.sqlite3.connect(state)
    store.execute("CREATE TABLE sessions (id TEXT, cwd TEXT, started_at REAL)")
    store.executemany(
        "INSERT INTO sessions VALUES (?,?,?)",
        [
            ("S-A", str(tmp_path.resolve()), row["created_at"] + 2.0),
            ("S-B", str(tmp_path.resolve()), row["created_at"] + 2.4),
        ],
    )
    store.commit()
    store.close()
    assert registry.link_hermes_sessions() == 0
    assert registry.get(row["id"])["native_session"] is None


def test_forked_claude_sessions_get_their_own_resumable_identity(tmp_path, monkeypatch):
    registry, _ = _registry(tmp_path, monkeypatch)
    parent = registry.create(
        name="agentik-claude-parent", kind="claude", cwd=tmp_path,
        command=["claude", "--session-id", "P"], native_session="P",
    )
    fork = registry.fork(parent, "agentik-claude-fork")
    command = agk.json.loads(fork["command_json"])
    # The fork keeps the launch wrapper and flags of a normal Claude session.
    base = agk.default_command("claude")
    assert command[:len(base)] == base
    assert command[len(base):len(base) + 3] == ["--resume", "P", "--fork-session"]
    assert fork["native_session"] not in {None, "P"}
    assert command[-2:] == ["--session-id", fork["native_session"]]

    # Until the fork is saved, a restart forks again from the parent.
    assert agk.resumable_command(tmp_path, fork) == command
    # Once saved it is resumed as itself: forking again would silently
    # branch a new conversation on every restart.
    transcript = tmp_path / ".claude/projects/-work" / f"{fork['native_session']}.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("{}\n", encoding="utf-8")
    assert agk.resumable_command(tmp_path, fork) == [*base, "--resume", fork["native_session"]]


def test_new_hermes_sessions_are_named_so_the_launch_itself_resumes(tmp_path, monkeypatch):
    registry, _ = _registry(tmp_path, monkeypatch)
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/bin/{name}")
    command, native = agk.launch_command("hermes", title="fix-copy")
    assert native is None
    assert command == ["/bin/hermes", "chat", "--continue", "fix-copy", "--create-if-missing"]
    assert agk.launch_command("hermes", None, "research", "local-gpt", "night")[0] == [
        "/bin/hermes", "--profile", "research", "chat", "--model", "local-gpt",
        "--continue", "night", "--create-if-missing",
    ]
    assert agk.launch_command("openrouter", title="or-run")[0] == [
        "/bin/hermes", "chat", "--provider", "openrouter", "--model", "stealth/ox-alpha",
        "--continue", "or-run", "--create-if-missing",
    ]
    # An explicit conversation still wins over naming a new one.
    assert agk.launch_command("hermes", "S-1", title="ignored")[0] == [
        "/bin/hermes", "--resume", "S-1"]

    row = registry.create(name="fix-copy", kind="hermes", cwd=tmp_path, command=command)
    assert agk.resumable_command(tmp_path, row) == command

    # Hermes records the conversation under that title at launch; the link
    # does not depend on when the first message is sent or on its directory.
    store = agk.sqlite3.connect(tmp_path / ".hermes/state.db") if (
        (tmp_path / ".hermes").mkdir() or True) else None
    store.execute("CREATE TABLE sessions(id TEXT, title TEXT, cwd TEXT, started_at REAL)")
    store.execute("INSERT INTO sessions VALUES('H-1','fix-copy','',?)", (row["created_at"] + 900,))
    store.execute("INSERT INTO sessions VALUES('H-2','other','',?)", (row["created_at"],))
    store.commit(); store.close()
    assert registry.link_hermes_sessions() == 1
    linked = registry.get("fix-copy")
    assert linked["native_session"] == linked["hermes_session"] == "H-1"
    assert agk.resumable_command(tmp_path, linked) == command

    # A reused name must not reopen the earlier conversation.
    assert agk.hermes_session_title(tmp_path, None, "fix-copy") == "fix-copy-2"
    assert agk.hermes_session_title(tmp_path, None, "brand-new") == "brand-new"
    assert agk.hermes_session_title(tmp_path, "absent", "fix-copy") == "fix-copy"


def test_codex_and_opencode_terminals_are_linked_from_the_cli_stores(tmp_path, monkeypatch):
    registry, _ = _registry(tmp_path, monkeypatch)
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    work = tmp_path / "work"; work.mkdir()
    other = tmp_path / "other"; other.mkdir()
    codex = registry.create(name="codex-work", kind="codex", cwd=work, command=["/bin/codex"])
    open_a = registry.create(name="open-a", kind="opencode", cwd=work, command=["/bin/opencode"])
    twin_a = registry.create(name="twin-a", kind="codex", cwd=other, command=["/bin/codex"])
    registry.create(name="twin-b", kind="codex", cwd=other, command=["/bin/codex"])
    assert registry.link_store_sessions() == 0

    started = int(codex["created_at"])
    (tmp_path / ".codex").mkdir()
    for version, rows in (("state_4", [("stale", str(work.resolve()), started + 1)]), ("state_5", [
        ("before", str(work.resolve()), started - 600),
        ("T-2", str(work.resolve()), started + 90),
        ("T-1", str(work.resolve()), started + 30),
        ("elsewhere", str(tmp_path), started + 5),
        ("T-twin", str(other.resolve()), started + 5),
    ])):
        store = agk.sqlite3.connect(tmp_path / f".codex/{version}.sqlite")
        store.execute("CREATE TABLE threads(id TEXT, cwd TEXT, created_at INTEGER, archived INTEGER DEFAULT 0)")
        store.executemany("INSERT INTO threads(id,cwd,created_at) VALUES(?,?,?)", rows)
        store.commit(); store.close()
    data = tmp_path / ".local/share/opencode"; data.mkdir(parents=True)
    store = agk.sqlite3.connect(data / "opencode.db")
    store.execute("CREATE TABLE session(id TEXT, parent_id TEXT, directory TEXT, time_created INTEGER)")
    store.executemany("INSERT INTO session VALUES(?,?,?,?)", [
        ("sub", "O-1", str(work.resolve()), (started + 20) * 1000),
        ("O-1", None, str(work.resolve()), (started + 40) * 1000),
    ])
    store.commit(); store.close()

    # The first conversation started in the terminal's directory after the
    # terminal was created; sub-agent sessions and other folders are ignored.
    assert registry.link_store_sessions() == 2
    assert registry.get("codex-work")["native_session"] == "T-1"
    assert registry.get("open-a")["native_session"] == "O-1"
    # Two unlinked terminals in one directory cannot be told apart.
    assert registry.get("twin-a")["native_session"] is None
    assert twin_a["native_session"] is None

    assert agk.resumable_command(tmp_path, registry.get("codex-work")) == [
        "/bin/codex", "resume", "T-1"]
    assert agk.resumable_command(tmp_path, registry.get("open-a")) == [
        "/bin/opencode", "--session", "O-1"]

    # Forks branch once, then resume their own conversation.
    fork = registry.fork(registry.get("open-a"), "open-fork")
    assert agk.json.loads(fork["command_json"]) == ["/bin/opencode", "--session", "O-1", "--fork"]
    assert fork["native_session"] is None
    codex_fork = registry.fork(registry.get("codex-work"), "codex-fork")
    assert agk.json.loads(codex_fork["command_json"]) == ["/bin/codex", "fork", "T-1"]
    assert registry.link_store_sessions() == 1
    assert registry.get("codex-fork")["native_session"] == "T-2"
    assert agk.resumable_command(tmp_path, registry.get("codex-fork")) == [
        "/bin/codex", "resume", "T-2"]


def test_a_model_can_be_chosen_for_every_provider(monkeypatch):
    monkeypatch.setattr(agk.shutil, "which", lambda name: f"/bin/{name}")
    assert agk.default_command("hermes", model="local-assistant") == [
        "/bin/hermes", "--model", "local-assistant"]
    assert agk.default_command("codex", model="gpt-x")[-2:] == ["--model", "gpt-x"]
    assert agk.default_command("opencode", model="anthropic/claude")[-2:] == [
        "--model", "anthropic/claude"]
    assert "--model" in agk.default_command("claude", model="opus")
    assert agk.default_command("openrouter", model="vendor/model:free")[-2:] == [
        "--model", "vendor/model:free"]
    assert agk.default_command("shell", model="ignored") == agk.default_command("shell")
    for unsafe in ("--yolo", "a b", "x;rm", ""):
        try:
            agk.default_command("hermes", model=unsafe)
        except ValueError:
            continue
        raise AssertionError(f"accepted unsafe model: {unsafe!r}")


def test_projects_are_detected_from_the_folders_that_hold_them(tmp_path, monkeypatch):
    home = tmp_path
    root = home / "projects"
    for path, text in (
        ("alpha/.git/HEAD", "ref: refs/heads/feature/x\n"), ("alpha/Cargo.toml", ""),
        ("alpha/package.json", "{}"), ("alpha/packages/inner/package.json", "{}"),
        ("beta/pyproject.toml", ""), ("clients/gamma/go.mod", ""),
        ("clients/loose/deep/package.json", "{}"), (".cache/.git/HEAD", "x"),
        ("node_modules/pkg/package.json", "{}"), ("notes.txt", "file"),
    ):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (root / "beta-link").symlink_to(root / "beta")

    # Without configuration every conventional folder that exists is used.
    assert agk.project_roots({}, home) == (root,)
    found = agk.discover_projects(agk.project_roots({}, home))
    assert [project["name"] for project in found] == ["alpha", "beta", "clients/gamma"]
    assert found[0]["stack"] == ["Rust", "Node"] and found[0]["branch"] == "feature/x"
    assert found[1]["branch"] is None and found[0]["status"] == "detected"

    # Configured roots are authoritative; missing and repeated ones drop out.
    (home / "lab").mkdir()
    config = {"projects_root": "~/projects", "project_roots": ["~/lab", "~/missing", "~/projects"]}
    assert agk.project_roots(config, home) == (root, home / "lab")

    monkeypatch.setenv("USER", "public-user")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGK_ENV_CONFIG", str(home / "absent.yaml"))
    monkeypatch.delenv("AGK_ENVIRONMENT", raising=False)
    env = agk.Environment.current()
    assert env.roots == (root,)
    assert [project["name"] for project in agk.all_projects(env)] == [
        "alpha", "beta", "clients/gamma"]


def test_hermes_skill_categories_are_not_listed_as_skills(tmp_path):
    for path in (".hermes/skills/apple/DESCRIPTION.md", ".hermes/skills/apple/notes/SKILL.md",
                 ".hermes/skills/legacy/DESCRIPTION.md", ".claude/skills/review/SKILL.md",
                 ".agents/skills/browser/SKILL.md"):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    env = agk.Environment("agentik", tmp_path, tmp_path / "projects")
    assert [(item["name"], item["source"]) for item in agk.skill_inventory(env)] == [
        ("browser", "shared"), ("legacy", "hermes"), ("notes", "hermes"), ("review", "claude")]
