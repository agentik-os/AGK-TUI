"""Metadata-only AGK Operative System and Hermes profile catalog."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml


class CatalogError(RuntimeError):
    pass


PERSONAL_OS_IDS = {
    "alignment-os", "decision-os", "goal-life-strategy-os", "habit-tracker-os",
    "health-energy-os", "identity-shift-os", "intuitive-os", "journal-os",
    "mentor-os", "mindset-os", "nutrition-os", "oto100m-os",
    "social-intelligence-os",
}
CANONICAL_OWNERS = {
    "builder-os": "operator",
    "evaluation-os": "operator",
    "research-os": "agentik",
    "strategy-os": "agentik",
    "youtube-os": "agentik",
    **{os_id: "private" for os_id in PERSONAL_OS_IDS},
}
_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class CatalogPaths:
    central_registry: Path
    private_registry: Path
    profile_roots: Mapping[str, Path]


@dataclass(frozen=True)
class OsControlRecord:
    os_id: str
    name: str
    version: str
    owner_environment: str
    linux_user: str
    profile_id: str
    profile_state: str
    agent_ids: tuple[str, ...]
    agent_state: str
    discord_mode: str
    discord_state: str
    lifecycle_state: str


def canonical_owner(os_id: str) -> str:
    value = str(os_id or "")
    if not _ID.fullmatch(value):
        raise CatalogError("invalid OS id")
    return CANONICAL_OWNERS.get(value, "agentik")


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _manifest(path: Path) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, yaml.YAMLError):
        return {}
    return value if isinstance(value, dict) else {}


def _version_key(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(value).split("."))
    except ValueError:
        return (0,)


def _central_packages(index_path: Path) -> dict[str, dict]:
    rows = _read_json(index_path).get("packages") or []
    result: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        os_id = str(row.get("id") or "")
        if _ID.fullmatch(os_id):
            result[os_id] = row
    return result


def _private_packages(registry_root: Path) -> dict[str, dict]:
    packages = registry_root / "packages"
    if not packages.is_dir() or packages.is_symlink():
        return {}
    result: dict[str, dict] = {}
    for os_home in sorted(packages.iterdir()):
        if not os_home.is_dir() or os_home.is_symlink() or not _ID.fullmatch(os_home.name):
            continue
        candidates = []
        for version_home in os_home.iterdir():
            manifest_path = version_home / "manifest.yaml"
            if version_home.is_dir() and not version_home.is_symlink() and manifest_path.is_file() and not manifest_path.is_symlink():
                row = _manifest(manifest_path)
                if str(row.get("id") or "") == os_home.name:
                    candidates.append(row)
        if candidates:
            result[os_home.name] = max(candidates, key=lambda row: _version_key(str(row.get("version") or "0")))
    return result


def _validate_roots(roots: Mapping[str, Path]) -> None:
    for environment in ("operator", "agentik", "mission", "private"):
        root = roots.get(environment)
        if root is None or not root.is_dir() or root.is_symlink():
            raise CatalogError(f"unsafe {environment} profile root")


def _profile_state(root: Path, profile_id: str) -> str:
    profile = root / "profiles" / profile_id
    if not profile.exists():
        return "missing"
    if not profile.is_dir() or profile.is_symlink():
        return "unsafe"
    required = (profile / "config.yaml", profile / "SOUL.md")
    return "ready" if all(path.is_file() and not path.is_symlink() for path in required) else "incomplete"


def _discord_mode(os_id: str) -> str:
    if os_id == "nutrition-os":
        return "dedicated"
    if os_id == "builder-os":
        return "environment"
    return "disabled"


def build_os_catalog(paths: CatalogPaths) -> list[OsControlRecord]:
    _validate_roots(paths.profile_roots)
    packages = _central_packages(paths.central_registry)
    packages.update(_private_packages(paths.private_registry))
    rows = []
    for os_id, package in sorted(packages.items()):
        owner = canonical_owner(os_id)
        profile_state = _profile_state(paths.profile_roots[owner], os_id)
        agents = tuple(str(value) for value in (package.get("agents") or []) if str(value).strip())
        mode = _discord_mode(os_id)
        rows.append(OsControlRecord(
            os_id=os_id,
            name=str(package.get("name") or os_id),
            version=str(package.get("version") or ""),
            owner_environment=owner,
            linux_user=owner,
            profile_id=os_id,
            profile_state=profile_state,
            agent_ids=agents,
            agent_state="declared" if agents else "missing",
            discord_mode=mode,
            discord_state="owner-prerequisite" if mode == "dedicated" else ("route-required" if mode == "environment" else "disabled"),
            lifecycle_state="staged" if profile_state != "ready" else "active",
        ))
    return rows
