import importlib.util
import json
import sqlite3
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "fleet_snapshot.py"


def load_module():
    spec = importlib.util.spec_from_file_location("fleet_snapshot_test", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_fixture(root: Path, org: str) -> dict[str, Path]:
    home = root / "home" / org
    hermes = home / ".hermes"
    board = hermes / "kanban" / "boards" / f"{org}-station"
    board.mkdir(parents=True)
    (hermes / "kanban" / "current").write_text(f"{org}-station\n")
    (board / "board.json").write_text(json.dumps({
        "slug": f"{org}-station", "name": f"{org.title()} Station",
        "description": "Station board", "icon": "◆", "color": "#7170ff",
        "archived": False,
    }))
    db = sqlite3.connect(board / "kanban.db")
    db.execute("CREATE TABLE tasks (id TEXT, title TEXT, assignee TEXT, status TEXT, priority INTEGER, created_at INTEGER, started_at INTEGER, completed_at INTEGER, session_id TEXT, project_id TEXT, block_kind TEXT)")
    db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
        "t_123", "Ship the dashboard", "default", "running", 3, 100, 110, None,
        "session-1", "project-1", None,
    ))
    db.commit(); db.close()

    state = sqlite3.connect(hermes / "state.db")
    state.execute("CREATE TABLE sessions (id TEXT, title TEXT, source TEXT, model TEXT, started_at REAL, ended_at REAL, last_activity_at REAL, message_count INTEGER, tool_call_count INTEGER, archived INTEGER, hidden INTEGER, profile_name TEXT)")
    state.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
        "session-1", "Dashboard build", "cli", "gpt-5.6-sol", 90, None, 120,
        4, 2, 0, 0, "default",
    ))
    state.commit(); state.close()

    agentik = home / ".agentik"
    agentik.mkdir()
    runtime = sqlite3.connect(agentik / "runtime.db")
    runtime.execute("CREATE TABLE runtime_sessions (id TEXT, name TEXT, type TEXT, environment TEXT, status TEXT, last_activity REAL, archived_at REAL, hermes_profile TEXT)")
    runtime.execute("INSERT INTO runtime_sessions VALUES (?,?,?,?,?,?,?,?)", (
        "r1", "builder", "hermes", org, "working", 121, None, "default",
    ))
    runtime.commit(); runtime.close()
    (agentik / "os-assignments.yaml").write_text(yaml.safe_dump({
        "schema_version": 1,
        "assignments": [{"os": "missing-os@0.1.0", "scope": "environment", "target": org}],
    }))

    agent_dir = hermes / "agents" / "builder"
    agent_dir.mkdir(parents=True)
    (agent_dir / "prompt.md").write_text("private prompt content")
    (agent_dir / "agent.yaml").write_text(yaml.safe_dump({
        "id": "builder", "name": "Builder", "version": "1.0.0",
        "description": "Builds verified artifacts", "scope": [org],
        "runtime": "hermes", "prompt": "prompt.md",
    }))
    profile_dir = hermes / "profiles" / "reviewer"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text("model:\n  default: gpt-test\n")
    return {"home": home, "hermes": hermes}


def test_snapshot_collects_only_bounded_operational_metadata(tmp_path):
    module = load_module()
    fixture = make_fixture(tmp_path, "operator")
    registry = tmp_path / "registry"
    package = registry / "packages" / "ops-os" / "1.0.0"
    package.mkdir(parents=True)
    (registry / "state").mkdir()
    (registry / "state" / "index.json").write_text(json.dumps({"packages": [{
        "id": "ops-os", "name": "Ops OS", "version": "1.0.0",
        "description": "Operations", "scope": ["operator"],
        "agents": ["builder"], "skills": [], "workflows": [], "tools": [],
        "commands": [], "knowledge": [], "evals": [], "dependencies": [],
        "capabilities": [],
    }]}))

    snapshot = module.collect_snapshot(
        homes={"operator": fixture["home"]}, registry_root=registry, now=200,
    )
    station = snapshot["organisations"]["operator"]
    assert station["kanban"]["counts"]["running"] == 1
    assert station["kanban"]["tasks"][0]["title"] == "Ship the dashboard"
    assert station["sessions"][0]["id"] == "session-1"
    assert station["agents"][0]["id"] == "builder"
    assert {agent["id"] for agent in station["agents"]} == {"builder", "reviewer"}
    assert next(agent for agent in station["agents"] if agent["id"] == "reviewer")["runtime"] == "hermes-profile"
    operating_systems = {item["id"]: item for item in station["os"]}
    assert operating_systems["missing-os"]["installed"] is False
    assert operating_systems["ops-os"]["installed"] is True
    assert station["runtimes"][0]["status"] == "working"
    encoded = json.dumps(snapshot)
    assert "private prompt content" not in encoded
    assert str(tmp_path) not in encoded


def test_atomic_write_uses_public_read_only_snapshot(tmp_path):
    module = load_module()
    target = tmp_path / "fleet-snapshot.json"
    module.atomic_write(target, {"schema": "agk.fleet.v1"})
    assert json.loads(target.read_text())["schema"] == "agk.fleet.v1"
    assert target.stat().st_mode & 0o777 == 0o640


def test_private_snapshot_merges_thirteen_owner_os_from_private_registry(tmp_path):
    module = load_module()
    homes = {}
    for name in ("operator", "agentik", "mission", "private"):
        home = tmp_path / name
        (home / ".hermes/profiles").mkdir(parents=True)
        homes[name] = home
    registry = tmp_path / "central"
    (registry / "state").mkdir(parents=True)
    (registry / "state/index.json").write_text(json.dumps({"packages": []}))
    personal_ids = {
        "alignment-os", "decision-os", "goal-life-strategy-os", "habit-tracker-os",
        "health-energy-os", "identity-shift-os", "intuitive-os", "journal-os",
        "mentor-os", "mindset-os", "nutrition-os", "oto100m-os",
        "social-intelligence-os",
    }
    packages = homes["private"] / ".agentik/os-registry/packages"
    for os_id in personal_ids:
        target = packages / os_id / "0.3.0"
        target.mkdir(parents=True)
        (target / "manifest.yaml").write_text(yaml.safe_dump({
            "id": os_id, "name": os_id, "version": "0.3.0",
            "agents": [f"{os_id}-operator"],
        }))

    snapshot = module.collect_snapshot(homes=homes, registry_root=registry, now=200)
    rows = snapshot["organisations"]["private"]["os"]

    assert {row["id"] for row in rows} == personal_ids
    assert all(row["owner_environment"] == "private" for row in rows)
    assert all(row["profile_id"] == row["id"] for row in rows)
    assert {row["profile_state"] for row in rows} == {"missing"}
