from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "hermes/plugins/platforms/discord/agk_os_control.py"
SPEC = importlib.util.spec_from_file_location("agk_os_control_tested", MODULE_PATH)
assert SPEC and SPEC.loader
control = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = control
SPEC.loader.exec_module(control)

PERSONAL_IDS = {
    "alignment-os", "decision-os", "goal-life-strategy-os", "habit-tracker-os",
    "health-energy-os", "identity-shift-os", "intuitive-os", "journal-os",
    "mentor-os", "mindset-os", "nutrition-os", "oto100m-os",
    "social-intelligence-os",
}


def make_paths(tmp_path: Path):
    central = tmp_path / "central/state/index.json"
    central.parent.mkdir(parents=True)
    central.write_text(json.dumps({"packages": [
        {"id": "builder-os", "name": "Builder OS", "version": "0.1.0", "agents": ["master-os-builder"]},
        {"id": "evaluation-os", "name": "Evaluation OS", "version": "0.1.0", "agents": ["evidence-auditor"]},
        {"id": "research-os", "name": "Research OS", "version": "0.1.0", "agents": ["oracle"]},
        {"id": "strategy-os", "name": "Strategy OS", "version": "0.1.0", "agents": ["product-strategy"]},
        {"id": "nutrition-os", "name": "Nutrition OS", "version": "1.1.0", "agents": ["nutrition-specialist"]},
    ]}))
    private = tmp_path / "private-registry/packages"
    for os_id in sorted(PERSONAL_IDS):
        target = private / os_id / "0.3.0"
        target.mkdir(parents=True)
        (target / "manifest.yaml").write_text(yaml.safe_dump({
            "id": os_id,
            "name": os_id.replace("-", " ").title(),
            "version": "0.3.0",
            "agents": [f"{os_id}-operator"],
        }))
    roots = {}
    for environment in ("operator", "agentik", "mission", "private"):
        root = tmp_path / "homes" / environment / ".hermes"
        (root / "profiles").mkdir(parents=True)
        roots[environment] = root
    return control.CatalogPaths(central, private.parent, roots)


def test_canonical_owners_are_stable():
    assert control.canonical_owner("builder-os") == "operator"
    assert control.canonical_owner("evaluation-os") == "operator"
    assert control.canonical_owner("research-os") == "agentik"
    assert control.canonical_owner("strategy-os") == "agentik"
    assert control.canonical_owner("nutrition-os") == "private"
    assert control.canonical_owner("mentor-os") == "private"


def test_private_catalog_exposes_thirteen_os_not_three_aggregators(tmp_path):
    rows = control.build_os_catalog(make_paths(tmp_path))
    private = [row for row in rows if row.owner_environment == "private"]
    assert {row.os_id for row in private} == PERSONAL_IDS
    assert all(row.profile_id == row.os_id for row in private)
    assert {row.profile_state for row in private} == {"missing"}
    assert not {"personal-operator", "personal-mentor", "personal-strategist"} & {
        row.profile_id for row in rows
    }


def test_catalog_deduplicates_nutrition_and_keeps_latest_private_version(tmp_path):
    rows = control.build_os_catalog(make_paths(tmp_path))
    nutrition = [row for row in rows if row.os_id == "nutrition-os"]
    assert len(nutrition) == 1
    assert nutrition[0].version == "0.3.0"
    assert nutrition[0].owner_environment == "private"
    assert len(rows) == 17


def test_symlinked_profile_root_is_rejected(tmp_path):
    paths = make_paths(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(real, target_is_directory=True)
    roots = dict(paths.profile_roots)
    roots["private"] = link
    with pytest.raises(control.CatalogError, match="profile root"):
        control.build_os_catalog(control.CatalogPaths(paths.central_registry, paths.private_registry, roots))


def test_catalog_reads_canonical_agent_binding_from_profile_distribution(tmp_path):
    paths = make_paths(tmp_path)
    profile = paths.profile_roots["operator"] / "profiles/builder-os"
    agent = profile / "agents/master-os-builder"
    agent.mkdir(parents=True)
    (profile / "config.yaml").write_text("model: gpt-test\n")
    (profile / "SOUL.md").write_text("# Builder\n")
    (profile / "distribution.yaml").write_text(yaml.safe_dump({
        "profile_id": "builder-os", "owner_environment": "operator",
        "agent_ids": ["master-os-builder"],
    }))
    (agent / "agent.yaml").write_text(yaml.safe_dump({
        "id": "master-os-builder", "profile": "builder-os",
    }))

    builder = next(row for row in control.build_os_catalog(paths) if row.os_id == "builder-os")

    assert builder.agent_ids == ("master-os-builder",)
    assert builder.agent_state == "ready"
