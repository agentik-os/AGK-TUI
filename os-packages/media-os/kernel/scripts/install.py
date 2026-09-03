#!/usr/bin/env python3
"""Transactionally install Media OS into an explicit offline root; never activate."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agentik_os.os_registry import OSRegistry
from media_os.doctor import CheckResult, CheckStatus, Doctor, LAYERS
from media_os.lifecycle import LifecycleService
from scripts.provision_media_os import (
    ProvisioningLifecycleCoordinator,
    build_lifecycle_snapshot_adapters,
    build_test_provision_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    root = args.offline_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    plan = build_test_provision_plan(
        root / "agentik" / ".hermes", args.source.resolve(), allowed_root=root,
        trust_root=root / "operator-trust",
    )
    registry = OSRegistry(root / "registry")
    coordinator = ProvisioningLifecycleCoordinator(plan)
    adapters = build_lifecycle_snapshot_adapters(plan, registry)
    doctor = Doctor({layer: (lambda layer=layer: CheckResult(layer, CheckStatus.NOT_CONFIGURED)) for layer in LAYERS})
    service = LifecycleService(
        deployment_id=plan.service_target, state_root=root / "state", registry=registry,
        doctor=doctor, smoke=lambda: False, coordinator=coordinator,
        snapshot_adapters=adapters,
    )
    result = service.install(args.source)
    print(f"{result.reference}: {result.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
