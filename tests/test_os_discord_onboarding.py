from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).parents[1]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


control = load(ROOT / "hermes/plugins/platforms/discord/agk_os_control.py", "os_control_onboarding")
installer = load(ROOT / "scripts/install-discord-token.py", "discord_token_installer_onboarding")


def state(member: bool):
    return control.DedicatedBotState(
        os_id="nutrition-os", owner_environment="private", profile_id="nutrition-os",
        application_id="1542135948475637861", guild_id="1541131439599386644",
        guild_member=member,
    )


def test_secure_input_is_hidden_before_oauth_membership():
    assert control.allowed_os_actions(state(False)) == {"oauth", "refresh", "back", "close"}
    assert "secure-input" in control.allowed_os_actions(state(True))


def test_oauth_url_is_locked_to_application_and_agk_guild():
    url = control.oauth_invite_url(state(False))
    query = parse_qs(urlparse(url).query)
    assert query["client_id"] == ["1542135948475637861"]
    assert query["guild_id"] == ["1541131439599386644"]
    assert query["disable_guild_select"] == ["true"]
    assert set(query["scope"][0].split()) == {"bot", "applications.commands"}


def test_secure_input_targets_only_the_private_os_profile(tmp_path):
    roots = {
        "operator": tmp_path / "operator/.hermes",
        "agentik": tmp_path / "agentik/.hermes",
        "mission": tmp_path / "mission/.hermes",
        "private": tmp_path / "private/.hermes",
    }
    for root in roots.values():
        (root / "profiles").mkdir(parents=True)
    request = control.create_os_secure_input(state(True), roots=roots, install_root=tmp_path / "installed")
    assert request.target == roots["private"] / "profiles/nutrition-os/.env"
    assert request.allowed_root == roots["private"] / "profiles/nutrition-os"
    assert request.installer[-2:] == ("--expected-application", "1542135948475637861")
    assert "1542135948475637861" not in str(request.target)


def test_installer_rejects_application_mismatch_before_write(tmp_path, monkeypatch):
    responses = {
        "/users/@me": {"id": "123", "username": "bot"},
        "/users/@me/guilds": [{"id": "1541131439599386644"}],
        "/oauth2/applications/@me": {"id": "123", "bot": {"id": "123"}},
    }
    monkeypatch.setattr(installer, "_discord_json", lambda path, _token: responses[path])
    target = tmp_path / ".hermes/profiles/nutrition-os/.env"
    target.parent.mkdir(parents=True)
    with pytest.raises(ValueError, match="expected application"):
        installer.install_token(
            "secret", target, expected_guild="1541131439599386644",
            expected_application="999", allowed_root=target.parent,
        )
    assert not target.exists()
