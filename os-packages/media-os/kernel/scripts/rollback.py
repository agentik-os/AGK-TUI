#!/usr/bin/env python3
"""Task 5 coordinator integration point for owned offline rollback."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from media_os.lifecycle import ActivationBlocked, LifecycleService
from media_os.doctor import ConcreteDoctor
from scripts.provision_media_os import ProvisioningLifecycleCoordinator


def run(coordinator: ProvisioningLifecycleCoordinator, service: LifecycleService) -> int:
    """Rollback through the real coordinator; no authority object leaves it."""
    if (type(coordinator) is not ProvisioningLifecycleCoordinator
            or type(service) is not LifecycleService
            or not service.has_authoritative_doctor()):
        print("rollback refused: concrete lifecycle doctor/readbacks required", file=sys.stderr)
        return 1
    try:
        result = coordinator.rollback(service)
    except (ActivationBlocked, ValueError):
        print("rollback refused: authoritative lifecycle rollback unavailable", file=sys.stderr)
        return 1
    print(f"active: {result.active_reference or 'none'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback must be invoked by the Task 5 provisioning coordinator integration.")
    parser.parse_args()
    print("rollback refused: the in-process Task 5 provisioning coordinator is required", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
