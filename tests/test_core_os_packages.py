import importlib.util
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "install_core_os_packages.py"


def load_module():
    spec = importlib.util.spec_from_file_location("install_core_os_test", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installs_versioned_packages_and_preserves_existing_registry(tmp_path):
    module = load_module()
    source = tmp_path / "source"
    package = source / "research-os"
    package.mkdir(parents=True)
    manifest = {
        "schema_version": "1.0", "id": "research-os", "name": "Research OS",
        "version": "0.1.0", "description": "Research", "scope": ["global", "operator"],
        "dependencies": [], "capabilities": ["research"], "skills": ["research"],
        "workflows": ["research-cycle"], "agents": ["oracle"], "tools": ["web"],
        "commands": [], "knowledge": ["README.md"], "evals": ["evals/cases.json"],
    }
    (package / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    (package / "README.md").write_text("Research package")
    (package / "evals").mkdir()
    (package / "evals" / "cases.json").write_text("[]")

    registry = tmp_path / "registry"
    (registry / "state").mkdir(parents=True)
    (registry / "packages" / "existing" / "1.0.0").mkdir(parents=True)
    (registry / "state" / "index.json").write_text(json.dumps({
        "schema_version": 1,
        "packages": [{"id": "existing", "version": "1.0.0"}],
    }))

    result = module.install_packages(source, registry)
    assert result == ["research-os@0.1.0"]
    assert (registry / "packages" / "research-os" / "0.1.0" / "manifest.yaml").is_file()
    index = json.loads((registry / "state" / "index.json").read_text())
    assert {(item["id"], item["version"]) for item in index["packages"]} == {
        ("existing", "1.0.0"), ("research-os", "0.1.0"),
    }


def test_reconciles_core_assignments_without_dropping_existing_records(tmp_path):
    module = load_module()
    homes = tmp_path / "home"
    for org in ("agentik", "mission", "private"):
        target = homes / org / ".agentik"
        target.mkdir(parents=True)
        (target / "os-assignments.yaml").write_text(yaml.safe_dump({
            "schema_version": 1,
            "assignments": [{"os": "custom-os@9.0.0", "scope": "environment", "target": org}],
        }))
    operator = tmp_path / "operator-assignments.yaml"
    (homes / "operator").mkdir(parents=True)
    module.reconcile_fleet_assignments(homes, operator)
    assert (operator.stat().st_mode & 0o777) == 0o640
    assert operator.stat().st_uid == (homes / "operator").stat().st_uid
    assert operator.stat().st_gid == (homes / "operator").stat().st_gid
    for org in ("operator", "agentik", "mission", "private"):
        path = operator if org == "operator" else homes / org / ".agentik" / "os-assignments.yaml"
        rows = yaml.safe_load(path.read_text())["assignments"]
        refs = {row["os"] for row in rows if row["target"] == org}
        assert {"research-os@0.1.0", "strategy-os@0.1.0", "builder-os@0.2.0", "evaluation-os@0.1.0"}.issubset(refs)
        assert "builder-os@0.1.0" not in refs
        if org != "operator":
            assert "custom-os@9.0.0" in refs


def test_projects_core_os_skills_into_default_and_named_hermes_profiles(tmp_path):
    module = load_module()
    source = tmp_path / "source"
    skill = source / "research-os" / "skills" / "evidence-research"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: evidence-research\ndescription: Use for research.\n---\n")
    homes = tmp_path / "home"
    for org in ("operator", "agentik", "mission", "private"):
        (homes / org / ".hermes" / "profiles" / "specialist").mkdir(parents=True)
    module.project_core_skills(source, homes)
    for org in ("operator", "agentik", "mission", "private"):
        assert (homes / org / ".hermes" / "skills" / "core-os" / "evidence-research" / "SKILL.md").is_file()
        assert (homes / org / ".hermes" / "profiles" / "specialist" / "skills" / "core-os" / "evidence-research" / "SKILL.md").is_file()


def test_rejects_path_or_identity_mismatch(tmp_path):
    module = load_module()
    source = tmp_path / "source"
    package = source / "research-os"
    package.mkdir(parents=True)
    (package / "manifest.yaml").write_text(yaml.safe_dump({
        "id": "wrong-id", "version": "0.1.0", "name": "Wrong", "description": "x",
        "scope": ["global"], "dependencies": [], "capabilities": [], "skills": [],
        "workflows": [], "agents": [], "tools": [], "commands": [], "knowledge": [], "evals": [],
    }))
    try:
        module.install_packages(source, tmp_path / "registry")
    except ValueError as error:
        assert "identity" in str(error)
    else:
        raise AssertionError("identity mismatch should fail")
