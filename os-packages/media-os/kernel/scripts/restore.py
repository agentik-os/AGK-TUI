#!/usr/bin/env python3
"""Restore a verified recovery archive to a fresh offline destination."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from media_os.recovery import restore_recovery_zip


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    destination = restore_recovery_zip(args.archive, args.destination, expected_sha256=args.sha256)
    print(destination); return 0


if __name__ == "__main__":
    raise SystemExit(main())
