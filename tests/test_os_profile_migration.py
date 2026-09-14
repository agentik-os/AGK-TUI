from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts/os_profile_migration.py"
SPEC = importlib.util.spec_from_file_location("os_profile_migration_tested", MODULE_PATH)
assert SPEC and SPEC.loader
migration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = migration
SPEC.loader.exec_module(migration)


def source_distribution(root: Path, os_id: str) -> Path:
    source = root / "sources" / os_id
    (source / "skills" / "runtime").mkdir(parents=True)
    (source / "distribution.yaml").write_text(f"name: {os_id}\nversion: 1.0.0\n")
    (source / "config.yaml").write_text("model:\n  default: gpt-test\n")
    (source / "SOUL.md").write_text(f"# {os_id}\n")
    (source / "skills/runtime/SKILL.md").write_text("---\nname: runtime\ndescription: test\n---\n")
    return source


def test_plan_is_read_only_and_creates_one_profile_per_os(tmp_path):
    homes = {name: tmp_path / name / ".hermes" for name in ("operator", "agentik", "mission", "private")}
    for home in homes.values():
        (home / "profiles").mkdir(parents=True)
    source = source_distribution(tmp_path, "builder-os")
    before = migration.tree_digest(tmp_path)

    plan = migration.build_migration_plan(
        [{"os_id": "builder-os", "owner_environment": "operator", "profile_id": "builder-os"}],
        migration.MigrationPaths(homes, {"builder-os": source}, tmp_path / "transactions"),
    )

    assert migration.tree_digest(tmp_path) == before
    assert [(row.profile_id, row.action) for row in plan.items] == [("builder-os", "create")]
    assert plan.mutation is False


def test_cross_home_secret_copy_is_rejected(tmp_path):
    operation = migration.CopyOperation(
        tmp_path / "operator/.hermes/.env",
        tmp_path / "private/.hermes/profiles/nutrition-os/.env",
    )
    with pytest.raises(migration.MigrationError, match="secret copy"):
        migration.validate_operation(operation)


def test_apply_is_idempotent_and_rollback_removes_only_transaction_owned_profile(tmp_path):
    homes = {name: tmp_path / name / ".hermes" for name in ("operator", "agentik", "mission", "private")}
    for home in homes.values():
        (home / "profiles").mkdir(parents=True)
    preexisting = homes["operator"] / "profiles/preexisting"
    preexisting.mkdir()
    source = source_distribution(tmp_path, "builder-os")
    paths = migration.MigrationPaths(homes, {"builder-os": source}, tmp_path / "transactions")
    plan = migration.build_migration_plan(
        [{"os_id": "builder-os", "owner_environment": "operator", "profile_id": "builder-os"}], paths,
    )

    first = migration.apply_profile_plan(plan)
    second = migration.apply_profile_plan(plan)

    assert first.created == (homes["operator"] / "profiles/builder-os",)
    assert second.created == ()
    assert second.reused == (homes["operator"] / "profiles/builder-os",)
    migration.rollback_profile_plan(first)
    assert preexisting.is_dir()
    assert not (homes["operator"] / "profiles/builder-os").exists()


def test_profile_root_symlink_is_rejected(tmp_path):
    homes = {name: tmp_path / name / ".hermes" for name in ("operator", "agentik", "mission", "private")}
    for home in homes.values():
        (home / "profiles").mkdir(parents=True)
    real = tmp_path / "real"; real.mkdir()
    (homes["operator"] / "profiles").rmdir()
    (homes["operator"] / "profiles").symlink_to(real, target_is_directory=True)
    with pytest.raises(migration.MigrationError, match="profile root"):
        migration.build_migration_plan([], migration.MigrationPaths(homes, {}, tmp_path / "transactions"))
