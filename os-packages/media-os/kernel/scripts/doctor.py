#!/usr/bin/env python3
"""Run Media OS doctor from concrete lifecycle adapters and readbacks."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agentik_os.os_registry import OSRegistry
from media_os.doctor import CheckStatus, ConcreteDoctor
from media_os.lifecycle import LifecycleService, build_concrete_lifecycle_doctor
from scripts.provision_media_os import (
    ProvisioningLifecycleCoordinator,
    build_lifecycle_snapshot_adapters,
    build_test_provision_plan,
)


def _doctor_from_root(root: Path, source: Path) -> LifecycleService:
    """Construct the operational doctor from the exact lifecycle resources."""
    root = Path(root).resolve()
    source = Path(source).resolve()
    if not root.is_dir() or root.is_symlink() or root not in source.parents:
        raise ValueError("offline doctor requires a package inside its concrete root")
    plan = build_test_provision_plan(
        root / "agentik/.hermes", source, allowed_root=root,
        trust_root=root / "operator-trust",
    )
    registry = OSRegistry(root / "registry")
    coordinator = ProvisioningLifecycleCoordinator(plan)
    adapters = build_lifecycle_snapshot_adapters(plan, registry)
    doctor = build_concrete_lifecycle_doctor(plan, registry, adapters)
    return LifecycleService(
        deployment_id=plan.service_target, state_root=root / "state",
        registry=registry, doctor=doctor, smoke=lambda: False,
        coordinator=coordinator, snapshot_adapters=adapters,
    )


def run(target: object) -> int:
    """Render only a doctor enrolled in one concrete lifecycle service."""
    if type(target) is not LifecycleService or not target.has_authoritative_doctor():
        print("MEDIA OS DOCTOR\nEVIDENCE: FAIL (concrete lifecycle service required)")
        return 1
    report = target.authoritative_doctor()
    print(report.render())
    return 0 if report.passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-root", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    source = args.source or args.offline_root / "package"
    try:
        service = _doctor_from_root(args.offline_root, source)
    except (OSError, TypeError, ValueError) as exc:
        print(f"MEDIA OS DOCTOR\nEVIDENCE: FAIL ({type(exc).__name__})")
        return 1
    return run(service)


if __name__ == "__main__":
    raise SystemExit(main())
