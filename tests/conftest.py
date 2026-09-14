"""CI-only stubs for optional Hermes runtime modules.

The production gateway provides these modules from the shared Hermes checkout.
Source-only CI intentionally does not install that runtime, so focused plugin
tests receive fail-closed empty providers until a test monkeypatches them.
"""
from __future__ import annotations

import importlib.util
import os
import pwd
import sys
import types


if importlib.util.find_spec("agent") is None:
    agent = types.ModuleType("agent")
    agent.__path__ = []
    account_usage = types.ModuleType("agent.account_usage")
    credential_pool = types.ModuleType("agent.credential_pool")

    def fetch_account_usage(*_args, **_kwargs):
        return None

    class EmptyPool:
        def entries(self):
            return []

    def load_pool(_provider):
        return EmptyPool()

    account_usage.fetch_account_usage = fetch_account_usage
    credential_pool.load_pool = load_pool
    agent.account_usage = account_usage
    agent.credential_pool = credential_pool
    sys.modules.update({
        "agent": agent,
        "agent.account_usage": account_usage,
        "agent.credential_pool": credential_pool,
    })

if importlib.util.find_spec("hermes_constants") is None:
    constants = types.ModuleType("hermes_constants")
    constants.set_hermes_home_override = lambda _path: None
    constants.reset_hermes_home_override = lambda _token: None
    sys.modules["hermes_constants"] = constants


_real_getpwnam = pwd.getpwnam
_station_users = {"operator", "agentik", "mission", "private"}
_missing_station_users = set(_station_users) if os.environ.get("AGK_TEST_MISSING_STATION_USERS") == "1" else set()
for _user in _station_users - _missing_station_users:
    try:
        _real_getpwnam(_user)
    except KeyError:
        _missing_station_users.add(_user)

if _missing_station_users:
    def _ci_getpwnam(name):
        if name in _missing_station_users:
            return pwd.struct_passwd((
                name, "x", os.getuid(), os.getgid(), "", f"/home/{name}", "/bin/bash",
            ))
        return _real_getpwnam(name)

    pwd.getpwnam = _ci_getpwnam
