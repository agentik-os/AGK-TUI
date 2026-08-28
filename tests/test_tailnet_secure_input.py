import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


secure = load("tailnet_secure_input_tested", "scripts/tailnet_secure_input.py")
discord_installer = load("install_discord_token_tested", "scripts/install-discord-token.py")


def test_bot_id_uses_canonical_lowercase_kebab_grammar():
    assert discord_installer.canonical_bot_id("nutrition-os") == "nutrition-os"
    assert discord_installer.canonical_bot_id("1password-os") == "1password-os"
    for invalid in ("Nutrition-OS", "nutrition_os", "-nutrition", "nutrition-", "nutrition--os", ""):
        with pytest.raises(ValueError, match="bot id"):
            discord_installer.canonical_bot_id(invalid)


def test_route_state_enforces_csrf_attempt_ttl_and_one_time_use(monkeypatch):
    now = [100.0]
    state = secure.RouteState("route", "csrf", ttl_seconds=1800, max_attempts=3, clock=lambda: now[0])
    assert state.authorize("csrf")
    assert not state.authorize("bad")
    assert state.attempts == 1
    state.attempts = 3
    assert not state.authorize("csrf")
    state.attempts = 0
    now[0] = 2000
    assert not state.authorize("csrf")
    now[0] = 100
    state.used = True
    assert not state.authorize("csrf")


def test_route_state_allows_only_one_submission_in_flight():
    state = secure.RouteState("route", "csrf")
    assert state.begin_submission("csrf")
    assert not state.begin_submission("csrf")
    state.finish_submission(False)
    assert state.attempts == 1
    assert state.begin_submission("csrf")
    state.finish_submission(True)
    assert state.used
    assert not state.begin_submission("csrf")


def test_unowned_rejection_cannot_release_active_submission():
    state = secure.RouteState("route", "csrf")
    assert state.begin_submission("csrf")
    state.record_rejection()
    assert state.in_flight
    assert not state.begin_submission("csrf")
    state.finish_submission(True)


def test_route_state_terminal_status_covers_use_expiry_and_attempt_exhaustion():
    now = [100.0]
    state = secure.RouteState("route", "csrf", ttl_seconds=10, clock=lambda: now[0])
    assert state.terminal_status is None
    state.attempts = state.max_attempts
    assert state.terminal_status == "EXPIRED"
    state.attempts = 0
    state.used = True
    assert state.terminal_status == "INSTALLED"
    state.used = False
    now[0] = 111.0
    assert state.terminal_status == "EXPIRED"


def test_body_parser_rejects_oversize_and_never_returns_csrf_as_secret():
    with pytest.raises(secure.IntakeError):
        secure.parse_submission(b"x" * 9000, 8192)
    secret, csrf = secure.parse_submission(b"csrf=abc&secret=token-value", 8192)
    assert secret == "token-value" and csrf == "abc"


def test_discord_validation_returns_bot_and_application_identity(monkeypatch):
    calls = []
    responses = {
        "/users/@me": {"id": "42", "username": "nutrition"},
        "/users/@me/guilds": [{"id": "99"}],
        "/oauth2/applications/@me": {"id": "84", "bot": {"id": "42"}},
    }

    def fake_discord_json(path, _secret):
        calls.append(path)
        return responses[path]

    monkeypatch.setattr(discord_installer, "_discord_json", fake_discord_json)

    assert discord_installer.validate_discord_token("candidate-value") == {
        "id": "42",
        "username": "nutrition",
        "application_id": "84",
        "guilds": ["99"],
    }
    assert calls == ["/users/@me", "/users/@me/guilds", "/oauth2/applications/@me"]


def test_discord_application_must_belong_to_validated_bot(monkeypatch):
    responses = {
        "/users/@me": {"id": "42", "username": "nutrition"},
        "/users/@me/guilds": [{"id": "99"}],
        "/oauth2/applications/@me": {"id": "84", "bot": {"id": "43"}},
    }
    monkeypatch.setattr(discord_installer, "_discord_json", lambda path, _secret: responses[path])

    with pytest.raises(ValueError, match="application identity"):
        discord_installer.validate_discord_token("candidate-value")


def test_invite_url_uses_application_id_and_least_privilege_permissions():
    assert discord_installer.invite_url("84") == (
        "https://discord.com/oauth2/authorize?client_id=84"
        "&scope=bot%20applications.commands&permissions=274877975552"
    )


def test_installer_rejection_does_not_persist(tmp_path, monkeypatch):
    target = tmp_path / ".env"
    monkeypatch.setattr(discord_installer, "validate_discord_token", lambda _secret: (_ for _ in ()).throw(ValueError("rejected")))
    with pytest.raises(ValueError):
        discord_installer.install_token("bad", target, expected_guild="1")
    assert not target.exists()


def test_success_stores_only_correct_vault_and_mode_0600(tmp_path, monkeypatch):
    root = tmp_path / "operator" / ".hermes"
    root.mkdir(parents=True)
    target = root / ".env"
    monkeypatch.setattr(discord_installer, "validate_discord_token", lambda _secret: {"id": "42", "username": "bot", "guilds": ["99"]})
    result = discord_installer.install_token("secret-value", target, expected_guild="99", allowed_root=root)
    assert result == {"id": "42", "username": "bot", "guild_id": "99"}
    assert "secret-value" in target.read_text(encoding="utf-8")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    outside = tmp_path / "other" / ".env"
    with pytest.raises(ValueError):
        discord_installer.install_token("secret-value", outside, expected_guild="99", allowed_root=root)


def test_dedicated_bot_stores_only_symbolic_key_and_preserves_default(tmp_path, monkeypatch):
    root = tmp_path / "mission" / ".hermes"
    root.mkdir(parents=True)
    target = root / ".env"
    target.write_text("DISCORD_BOT_TOKEN=default-value\n", encoding="utf-8")
    monkeypatch.setattr(
        discord_installer,
        "validate_discord_token",
        lambda _secret: {
            "id": "42",
            "username": "nutrition",
            "application_id": "84",
            "guilds": ["99"],
        },
    )

    result = discord_installer.install_token(
        "dedicated-value",
        target,
        expected_guild="99",
        allowed_root=root,
        bot_id="nutrition-os",
    )

    assert result == {
        "id": "42",
        "username": "nutrition",
        "application_id": "84",
        "guild_id": "99",
    }
    assert target.read_text(encoding="utf-8").splitlines() == [
        "DISCORD_BOT_TOKEN=default-value",
        "DISCORD_BOT_NUTRITION_OS_TOKEN=dedicated-value",
    ]
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_atomic_store_does_not_follow_preexisting_temporary_symlink(tmp_path, monkeypatch):
    root = tmp_path / "operator" / ".hermes"
    root.mkdir(parents=True)
    target = root / ".env"
    outside = tmp_path / "outside"
    outside.write_text("preserve\n", encoding="utf-8")
    target.with_name("." + target.name + ".discord-token-new").symlink_to(outside)
    monkeypatch.setattr(
        discord_installer,
        "validate_discord_token",
        lambda _secret: {
            "id": "42",
            "username": "bot",
            "application_id": "84",
            "guilds": ["99"],
        },
    )

    discord_installer.install_token(
        "candidate-value",
        target,
        expected_guild="99",
        allowed_root=root,
        bot_id="nutrition-os",
    )

    assert outside.read_text(encoding="utf-8") == "preserve\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_discord_identity_requires_exact_guild_before_storage(tmp_path, monkeypatch):
    root = tmp_path / ".hermes"; root.mkdir()
    target = root / ".env"
    monkeypatch.setattr(discord_installer, "validate_discord_token", lambda _secret: {"id": "42", "username": "bot", "guilds": ["98"]})
    with pytest.raises(ValueError, match="guild"):
        discord_installer.install_token("secret-value", target, expected_guild="99", allowed_root=root)
    assert not target.exists()


def test_ui_contract_is_monochrome_masked_neutral_and_accessible():
    html = secure.render_page("/route", "csrf", "READY", "WireGuard-protected Tailnet transport")
    assert "-webkit-text-security: disc" in html
    assert 'autocomplete="off"' in html
    assert "data-lpignore" in html
    assert "Show" in html and "aria-label" in html
    assert "linear-gradient" not in html
    assert "box-shadow" not in html
    assert ":focus" in html and "outline: none" in html
    assert "#6" not in html  # no colored focus hex accents


def test_stdout_contract_returns_only_authorized_public_fields(capsys):
    payload = {
        "status": "INSTALLED",
        "id": "42",
        "username": "nutrition",
        "application_id": "84",
        "guild_id": "99",
        "invite_url": "https://discord.com/example",
        "target": "/vault/.env",
        "guilds": ["99"],
        "token": "candidate-value",
    }
    result = secure.safe_result(payload)
    print(json.dumps(result))
    captured = capsys.readouterr()
    assert result == {
        "id": "42",
        "username": "nutrition",
        "application_id": "84",
        "guild_id": "99",
        "invite_url": "https://discord.com/example",
    }
    assert "candidate-value" not in captured.out + captured.err
    assert "/vault/.env" not in captured.out + captured.err


def test_installer_success_payload_is_fail_closed():
    valid = json.dumps({
        "status": "INSTALLED",
        "id": "42",
        "username": "nutrition",
        "application_id": "84",
        "guild_id": "99",
        "invite_url": "https://discord.com/example",
    })
    assert secure.parse_installer_result(valid) == {
        "id": "42",
        "username": "nutrition",
        "application_id": "84",
        "guild_id": "99",
        "invite_url": "https://discord.com/example",
    }
    for invalid in ("", "not-json", "[]", "{}", json.dumps({"status": "INSTALLED", "id": "42"})):
        with pytest.raises(secure.IntakeError, match="installer result"):
            secure.parse_installer_result(invalid)


def test_agk_cli_and_future_install_expose_secure_input():
    control = (ROOT / "scripts/agk_control.py").read_text(encoding="utf-8")
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'sub.add_parser("secure-input")' in control
    assert 'secure.add_argument("--bot-id", type=canonical_bot_id)' in control
    assert 'installer.extend(["--bot-id", args.bot_id])' in control
    assert "tailnet_secure_input.py" in control
    assert 'install -m 0755 "$repo_root/scripts/tailnet_secure_input.py"' in install
    assert 'install -m 0755 "$repo_root/scripts/install-discord-token.py"' in install


def test_secure_input_requires_station_magicdns_https():
    assert secure.require_https_url("https://station.tailnet.ts.net/route", "station.tailnet.ts.net") == (
        "https://station.tailnet.ts.net/route"
    )
    for invalid in (
        "http://100.64.0.1:8080/route",
        "http://localhost:8080/route",
        "https://public.example/route",
    ):
        with pytest.raises(secure.IntakeError, match="HTTPS"):
            secure.require_https_url(invalid, "station.tailnet.ts.net")


def test_no_serve_requires_explicit_test_environment():
    with pytest.raises(secure.IntakeError, match="test-only"):
        secure.validate_transport_mode(True, {})
    secure.validate_transport_mode(True, {"AGK_SECURE_INPUT_TEST_ONLY": "1"})
    secure.validate_transport_mode(False, {})


def test_terminal_response_schedules_shutdown_even_when_send_fails():
    stopped = threading.Event()

    class Server:
        def shutdown(self):
            stopped.set()

    def broken_send(*_args):
        raise BrokenPipeError

    with pytest.raises(BrokenPipeError):
        secure.send_terminal_response(Server(), broken_send, 200, "INSTALLED", {})
    assert stopped.wait(1)


def test_serve_close_removes_only_lease_route_without_full_restore(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(secure.subprocess, "run", fake_run)
    lease = secure.ServeLease("/route", "http://100.64.0.1:1234/route", "station.ts.net")
    lease.active = True
    lease.close()

    assert any(argv[-1] == "off" and "/route" in argv for argv in calls)
    assert not any("set-config" in argv for argv in calls)
