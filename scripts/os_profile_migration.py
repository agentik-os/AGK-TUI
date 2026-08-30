#!/usr/bin/env python3
"""Preview-first, recoverable Hermes profile ownership migration."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


class MigrationError(RuntimeError):
    pass


_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FORBIDDEN = {".env", "auth.json", "state.db", "state.db-wal", "state.db-shm"}
_FORBIDDEN_DIRS = {"memories", "sessions", "logs", "cache", "cron"}


@dataclass(frozen=True)
class MigrationPaths:
    homes: Mapping[str, Path]
    sources: Mapping[str, Path]
    transaction_root: Path


@dataclass(frozen=True)
class PlanItem:
    os_id: str
    owner_environment: str
    profile_id: str
    source: Path | None
    target: Path
    action: str
    reason: str


@dataclass(frozen=True)
class MigrationPlan:
    paths: MigrationPaths
    items: tuple[PlanItem, ...]
    mutation: bool = False


@dataclass(frozen=True)
class MigrationReceipt:
    transaction_id: str
    created: tuple[Path, ...]
    reused: tuple[Path, ...]
    manifest: Path


@dataclass(frozen=True)
class CopyOperation:
    source: Path
    destination: Path


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return digest.hexdigest()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        digest.update(str(relative).encode("utf-8") + b"\0" + path.read_bytes())
    return digest.hexdigest()


def validate_operation(operation: CopyOperation) -> None:
    names = set(operation.source.parts) | set(operation.destination.parts)
    if operation.source.name in _FORBIDDEN or operation.destination.name in _FORBIDDEN or names & _FORBIDDEN_DIRS:
        raise MigrationError("secret copy is forbidden")


def _validate_paths(paths: MigrationPaths) -> None:
    for environment in ("operator", "agentik", "mission", "private"):
        home = paths.homes.get(environment)
        profiles = home / "profiles" if home is not None else None
        if home is None or not home.is_dir() or home.is_symlink() or profiles is None or not profiles.is_dir() or profiles.is_symlink():
            raise MigrationError(f"unsafe {environment} profile root")


def _safe_source(source: Path) -> bool:
    if not source.is_dir() or source.is_symlink():
        return False
    required = (source / "distribution.yaml", source / "config.yaml")
    if not all(path.is_file() and not path.is_symlink() for path in required):
        return False
    for path in source.rglob("*"):
        if path.is_symlink() or path.name in _FORBIDDEN or set(path.parts) & _FORBIDDEN_DIRS:
            return False
    return True


def build_migration_plan(records: Iterable[Mapping[str, str]], paths: MigrationPaths) -> MigrationPlan:
    _validate_paths(paths)
    items = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        os_id = str(record.get("os_id") or "")
        owner = str(record.get("owner_environment") or "")
        profile_id = str(record.get("profile_id") or os_id)
        if not _ID.fullmatch(os_id) or not _ID.fullmatch(profile_id) or owner not in paths.homes:
            raise MigrationError("invalid migration identity")
        identity = (owner, profile_id)
        if identity in seen:
            raise MigrationError("duplicate profile target")
        seen.add(identity)
        target = paths.homes[owner] / "profiles" / profile_id
        source = paths.sources.get(os_id)
        if target.exists():
            if not target.is_dir() or target.is_symlink():
                raise MigrationError("unsafe profile target")
            action, reason = "reuse", "profile exists"
        elif source is None:
            action, reason = "blocked", "distribution source missing"
        elif not _safe_source(source):
            action, reason = "blocked", "distribution source unsafe"
        else:
            action, reason = "create", "profile missing"
        items.append(PlanItem(os_id, owner, profile_id, source, target, action, reason))
    return MigrationPlan(paths, tuple(items), False)


def _copy_distribution(source: Path, target: Path) -> None:
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if path.is_symlink() or path.name in _FORBIDDEN or set(relative.parts) & _FORBIDDEN_DIRS:
                raise MigrationError("secret copy is forbidden")
            destination = staging / relative
            if path.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            elif path.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        os.replace(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def apply_profile_plan(plan: MigrationPlan) -> MigrationReceipt:
    _validate_paths(plan.paths)
    blocked = [item for item in plan.items if item.action == "blocked"]
    if blocked:
        raise MigrationError("migration plan contains blocked items")
    transaction_id = uuid.uuid4().hex
    created: list[Path] = []
    reused: list[Path] = []
    for item in plan.items:
        if item.target.exists():
            reused.append(item.target)
            continue
        if item.source is None or not _safe_source(item.source):
            raise MigrationError("distribution source unavailable")
        _copy_distribution(item.source, item.target)
        created.append(item.target)
    plan.paths.transaction_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = plan.paths.transaction_root / f"{transaction_id}.json"
    payload = {
        "schema": "agk.os-profile-migration.v1",
        "transaction_id": transaction_id,
        "created": [str(path) for path in created],
        "reused": [str(path) for path in reused],
        "created_at": time.time(),
    }
    temporary = manifest.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.chmod(0o600)
    os.replace(temporary, manifest)
    return MigrationReceipt(transaction_id, tuple(created), tuple(reused), manifest)


def rollback_profile_plan(receipt: MigrationReceipt) -> None:
    for target in reversed(receipt.created):
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
    if receipt.manifest.is_file():
        data = json.loads(receipt.manifest.read_text())
        data["rolled_back_at"] = time.time()
        temporary = receipt.manifest.with_suffix(".rollback.tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        temporary.chmod(0o600)
        os.replace(temporary, receipt.manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("inspect", "plan"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = {"action": args.action, "mutation": False, "status": "requires-explicit-record-input"}
    print(json.dumps(payload, sort_keys=True) if args.json else payload["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
