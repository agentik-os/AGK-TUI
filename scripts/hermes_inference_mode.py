#!/usr/bin/env python3
"""Alias entrypoint: Hermes dual inference-mode switch (free|pro|status)."""
import os
import sys
from pathlib import Path

TARGET = Path(__file__).with_name("fleet_provider_switch.py")
os.execv(sys.executable, [sys.executable, str(TARGET), *sys.argv[1:]])
