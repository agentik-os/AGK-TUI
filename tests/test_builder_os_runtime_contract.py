from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
BUILDER = ROOT / "os-packages/builder-os"
MASTER = ROOT / "hermes/agents/master-os-builder/workflow.yaml"


def test_builder_os_requires_runtime_contract():
    manifest = yaml.safe_load((BUILDER / "manifest.yaml").read_text())
    assert manifest["version"] == "0.2.0"
    assert "runtime-contract" in manifest["capabilities"]
    assert "os-runtime-delivery" in manifest["workflows"]
    assert set(manifest["runtime_contract"]["required"]) == {
        "canonical-owner", "hermes-profile", "owning-agent", "provider-fallback",
        "discord-mode", "doctor", "rollback",
    }


def test_build_cycle_cannot_finish_before_runtime_delivery():
    workflow = yaml.safe_load((BUILDER / "workflows/build-cycle.yaml").read_text())
    stages = {row["id"]: row for row in workflow["stages"]}
    assert stages["os-runtime-delivery"]["requires"] == ["verify"]
    assert stages["complete"]["requires"] == ["os-runtime-delivery"]
    assert stages["complete"]["output"] == "runtime-accepted-os"


def test_master_builder_uses_the_same_profile_agent_and_discord_invariants():
    workflow = yaml.safe_load(MASTER.read_text())
    invariants = "\n".join(workflow["invariants"])
    assert "one canonical Hermes profile" in invariants
    assert "owning agent" in invariants
    assert "explicit Discord mode" in invariants
    integrate = next(row for row in workflow["phases"] if row["id"] == "integrate")
    gates = "\n".join(integrate["gates"])
    assert "provider and independently usable fallback" in gates
    assert "doctor and rollback" in gates


def test_builder_package_embeds_its_canonical_hermes_profile_and_agent_binding():
    profile = BUILDER / "profile"
    assert (profile / "distribution.yaml").is_file()
    assert (profile / "config.yaml").is_file()
    assert (profile / "SOUL.md").is_file()
    assert (profile / "skills/verified-builder/SKILL.md").is_file()
    distribution = yaml.safe_load((profile / "distribution.yaml").read_text())
    assert distribution["profile_id"] == "builder-os"
    assert distribution["owner_environment"] == "operator"
    assert distribution["provider"]["primary"] == "openai-codex"
    assert distribution["provider"]["fallback"] == "agk-gemma-local"
    agent = yaml.safe_load((ROOT / "hermes/agents/master-os-builder/agent.yaml").read_text())
    assert agent["profile"] == "builder-os"
