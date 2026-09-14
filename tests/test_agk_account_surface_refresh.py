from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "hermes/plugins/platforms/discord/adapter.py"


class LoggerSpy:
    def __init__(self):
        self.info_calls = []
        self.warning_calls = []

    def info(self, *args):
        self.info_calls.append(args)

    def warning(self, *args):
        self.warning_calls.append(args)


def _load_refresh_account_surfaces(logger):
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))
    adapter_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DiscordAdapter"
    )
    method = next(
        node
        for node in adapter_class.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "refresh_account_surfaces"
    )
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    namespace = {"logger": logger}
    exec(compile(module, str(ADAPTER), "exec"), namespace)
    return namespace["refresh_account_surfaces"]


class Surface:
    def __init__(self, method_name: str, error: Exception | None = None):
        self.method_name = method_name
        self.error = error
        self.calls = 0

    async def refresh_message(self):
        assert self.method_name == "refresh_message"
        self.calls += 1
        if self.error:
            raise self.error

    async def refresh_once(self):
        assert self.method_name == "refresh_once"
        self.calls += 1
        if self.error:
            raise self.error


async def _forbidden_lifecycle(*_args, **_kwargs):
    raise AssertionError("account surface refresh must not touch lifecycle methods")


def _adapter(view=None, monitor=None):
    return SimpleNamespace(
        name="Discord",
        _account_control_view=view,
        _account_usage_monitor=monitor,
        start=_forbidden_lifecycle,
        stop=_forbidden_lifecycle,
        restart=_forbidden_lifecycle,
    )


@pytest.mark.asyncio
async def test_refresh_account_surfaces_attempts_each_present_surface_exactly_once():
    logger = LoggerSpy()
    refresh = _load_refresh_account_surfaces(logger)
    view = Surface("refresh_message")
    monitor = Surface("refresh_once")

    result = await refresh(_adapter(view, monitor), reason="account-transaction")

    assert result == {}
    assert view.calls == 1
    assert monitor.calls == 1
    assert logger.warning_calls == []


@pytest.mark.asyncio
async def test_refresh_account_surfaces_skips_absent_surfaces():
    logger = LoggerSpy()
    refresh = _load_refresh_account_surfaces(logger)

    assert await refresh(_adapter(), reason="account-transaction") == {}
    assert logger.warning_calls == []


@pytest.mark.asyncio
async def test_refresh_account_surfaces_isolates_persistent_post_failure():
    logger = LoggerSpy()
    refresh = _load_refresh_account_surfaces(logger)
    view = Surface("refresh_message", RuntimeError("secret provider response"))
    monitor = Surface("refresh_once")

    result = await refresh(_adapter(view, monitor), reason="account-transaction")

    assert result == {"persistent_post": "RuntimeError"}
    assert view.calls == 1
    assert monitor.calls == 1
    warning_text = repr(logger.warning_calls)
    assert "RuntimeError" in warning_text
    assert "secret provider response" not in warning_text


@pytest.mark.asyncio
async def test_refresh_account_surfaces_reports_monitor_failure_by_class_only():
    logger = LoggerSpy()
    refresh = _load_refresh_account_surfaces(logger)
    view = Surface("refresh_message")
    monitor = Surface("refresh_once", ValueError("credential detail"))

    result = await refresh(_adapter(view, monitor), reason="account-transaction")

    assert result == {"usage_monitor": "ValueError"}
    assert view.calls == 1
    assert monitor.calls == 1
    warning_text = repr(logger.warning_calls)
    assert "ValueError" in warning_text
    assert "credential detail" not in warning_text
