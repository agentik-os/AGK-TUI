from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
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


def test_finalization_commands_enable_route_persistence_and_doctor():
    commands = installer.finalization_commands(
        "nutrition-os", "1542137541572956193", hermes_bin="/usr/local/bin/hermes"
    )

    assert commands == [
        ["/usr/local/bin/hermes", "--profile", "nutrition-os", "config", "set", "platforms.discord.enabled", "true"],
        ["/usr/local/bin/hermes", "--profile", "nutrition-os", "config", "set", "platforms.discord.gateway_restart_notification", "false"],
        ["/usr/local/bin/hermes", "--profile", "nutrition-os", "config", "set", "discord.require_mention", "true"],
        ["/usr/local/bin/hermes", "--profile", "nutrition-os", "config", "set", "discord.allowed_channels", "1542137541572956193"],
        ["/usr/local/bin/hermes", "--profile", "nutrition-os", "config", "set", "discord.free_response_channels", "1542137541572956193"],
        ["/usr/local/bin/hermes", "--profile", "nutrition-os", "config", "set", "agent.restart_after_turn_timeout", "1800"],
        ["/usr/local/bin/hermes", "--profile", "nutrition-os", "config", "set", "agent.restart_drain_timeout", "1800"],
        ["/usr/local/bin/hermes", "--profile", "nutrition-os", "gateway", "install", "--force", "--start-now", "--start-on-login"],
        ["/usr/local/bin/hermes", "--profile", "nutrition-os", "doctor"],
    ]


def test_finalize_profile_requires_fresh_connected_writer_and_writes_public_receipt(tmp_path):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    calls = []
    states = iter([
        {"gateway_state": "running", "pid": 41, "start_time": 10, "platforms": {"discord": {"state": "connected", "writer_pid": 40, "writer_start_time": 9}}},
        {"gateway_state": "running", "pid": 42, "start_time": 20, "platforms": {"discord": {"state": "connected", "writer_pid": 42, "writer_start_time": 20}}},
        {"gateway_state": "running", "pid": 42, "start_time": 20, "platforms": {"discord": {"state": "connected", "writer_pid": 42, "writer_start_time": 20}}},
    ])
    service_root = tmp_path / ".config/systemd/user"
    service_states = iter([
        {"known": True, "load_state": "not-found", "active_state": "inactive", "unit_file_state": "", "active": False, "enabled": False, "unit_path": None},
        {"known": True, "load_state": "loaded", "active_state": "active", "unit_file_state": "enabled", "active": True, "enabled": True, "unit_path": str(service_root / "hermes-gateway-nutrition-os.service")},
    ])

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    def read_state(path):
        state = next(states)
        path.write_text(json.dumps(state))
        return state

    receipt = installer.finalize_profile(
        profile,
        profile_id="nutrition-os",
        home_channel="1542137541572956193",
        application_id="1542135948475637861",
        guild_id="1541131439599386644",
        hermes_bin="/usr/local/bin/hermes",
        runner=run,
        state_reader=read_state,
        wait=lambda _seconds: None,
        attempts=2,
        service_config_root=service_root,
        service_state_reader=lambda _unit: next(service_states),
        process_alive=lambda pid, _profile: pid == 42,
        process_start_time=lambda pid: 20 if pid == 42 else None,
        state_mtime=lambda _path: 200.0,
        wall_clock=lambda: 100.0,
        canonical_profiles_root=profile.parent,
    )

    assert calls == installer.finalization_commands(
        "nutrition-os", "1542137541572956193", hermes_bin="/usr/local/bin/hermes"
    )
    assert receipt["gateway"] == "connected"
    assert receipt["application_id"] == "1542135948475637861"
    with pytest.raises(StopIteration):
        next(service_states)
    stored = json.loads((profile / "discord-install-receipt.json").read_text())
    assert stored == receipt
    assert (profile / "discord-install-receipt.json").stat().st_mode & 0o777 == 0o600
    assert "token" not in json.dumps(stored).lower()
    drop_in = tmp_path / ".config/systemd/user/hermes-gateway-nutrition-os.service.d/30-station-runtime.conf"
    assert drop_in.read_text() == "[Service]\nTimeoutStopSec=1860\n"
    assert drop_in.stat().st_mode & 0o777 == 0o600


def test_finalization_failure_restores_previous_env(tmp_path, monkeypatch):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    (profile / "distribution.yaml").write_text("owner_environment: private\nprofile_id: nutrition-os\nos_id: nutrition-os\nversion: 0.3.0\n")
    target = profile / ".env"
    target.write_text("UNCHANGED=1\n", encoding="utf-8")
    monkeypatch.setattr(installer, "validate_discord_token", lambda _secret: {
        "id": "1542135948475637861", "username": "Nutrition OS",
        "application_id": "1542135948475637861", "guilds": ["1541131439599386644"],
    })

    def fail(**_kwargs):
        raise RuntimeError("gateway did not connect")

    with pytest.raises(RuntimeError, match="gateway did not connect"):
        installer.install_token(
            "secret", target,
            expected_guild="1541131439599386644",
            expected_application="1542135948475637861",
            allowed_root=profile,
            home_channel="1542137541572956193",
            profile_id="nutrition-os",
            expected_os_id="nutrition-os",
            expected_os_version="0.3.0",
            finalizer=fail,
            preflight=lambda **_kwargs: None,
            rollback_guard=lambda **_kwargs: None,
        )

    assert target.read_text(encoding="utf-8") == "UNCHANGED=1\n"


def test_managed_env_keys_are_deduplicated_and_cannot_override_later():
    rows = installer._replace_env_values(
        [
            "A=1",
            "DISCORD_BOT_TOKEN=old-one",
            "DISCORD_ALLOWED_CHANNELS=*",
            "export DISCORD_BOT_TOKEN=exported-old",
            "DISCORD_BOT_TOKEN=old-two",
            "DISCORD_ALLOWED_CHANNELS=other",
        ],
        {"DISCORD_BOT_TOKEN": "validated", "DISCORD_ALLOWED_CHANNELS": "123456789012345"},
    )
    assert rows == [
        "A=1",
        "DISCORD_BOT_TOKEN=validated",
        "DISCORD_ALLOWED_CHANNELS=123456789012345",
    ]


def test_installer_persists_loop_safe_bot_admission_defaults(tmp_path, monkeypatch):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    (profile / "distribution.yaml").write_text(
        "owner_environment: private\nprofile_id: nutrition-os\nos_id: nutrition-os\nversion: 0.3.0\n",
        encoding="utf-8",
    )
    target = profile / ".env"
    target.write_text("", encoding="utf-8")
    monkeypatch.setattr(installer, "validate_discord_token", lambda _secret: {
        "id": "1542135948475637861",
        "username": "Nutrition OS",
        "application_id": "1542135948475637861",
        "guilds": ["1541131439599386644"],
    })

    installer.install_token(
        "secret",
        target,
        expected_guild="1541131439599386644",
        expected_application="1542135948475637861",
        allowed_root=profile,
        home_channel="1542137541572956193",
        profile_id="nutrition-os",
        expected_os_id="nutrition-os",
        expected_os_version="0.3.0",
        preflight=lambda **_kwargs: None,
        finalizer=lambda **_kwargs: None,
    )

    values = dict(
        line.split("=", 1)
        for line in target.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    assert values["DISCORD_ALLOW_ALL_USERS"] == "false"
    assert values["DISCORD_ALLOW_BOTS"] == "mentions"
    assert values["DISCORD_BOTS_REQUIRE_INLINE_MENTION"] == "true"


def test_proc_start_time_parser_handles_parenthesized_comm_with_spaces():
    raw = "123 (hermes gateway worker) " + " ".join(["S"] + ["0"] * 18 + ["987654"])
    assert installer._parse_proc_start_time(raw) == 987654


def test_gateway_argv_fingerprint_is_exact():
    expected = [
        "/opt/agk-terminal/hermes-agent/venv/bin/python", "-m", "hermes_cli.main",
        "--profile", "nutrition-os", "gateway", "run",
    ]
    assert installer._gateway_argv_matches(expected, "nutrition-os")
    assert not installer._gateway_argv_matches([expected[0] + "-malicious", *expected[1:]], "nutrition-os")
    assert not installer._gateway_argv_matches(["extra", *expected], "nutrition-os")
    assert not installer._gateway_argv_matches([*expected, "extra"], "nutrition-os")


def test_active_gateway_is_rejected_before_any_finalization_command(tmp_path):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    calls = []

    with pytest.raises(ValueError, match="rotation workflow"):
        installer.finalize_profile(
            profile,
            profile_id="nutrition-os",
            home_channel="1542137541572956193",
            application_id="1542135948475637861",
            guild_id="1541131439599386644",
            runner=lambda command, **_kwargs: calls.append(command),
            service_state_reader=lambda _unit: {"known": True, "load_state": "loaded", "active": True, "enabled": True, "unit_path": "existing"},
            service_config_root=tmp_path / ".config/systemd/user",
            canonical_profiles_root=profile.parent,
        )

    assert calls == []


def test_service_preflight_runs_before_submitted_credential_is_written(tmp_path, monkeypatch):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    (profile / "distribution.yaml").write_text("owner_environment: private\nprofile_id: nutrition-os\nos_id: nutrition-os\nversion: 0.3.0\n")
    target = profile / ".env"
    target.write_text("DISCORD_BOT_TOKEN=previous\n")
    monkeypatch.setattr(installer, "validate_discord_token", lambda _secret: {
        "id": "1542135948475637861", "username": "Nutrition OS",
        "application_id": "1542135948475637861", "guilds": ["1541131439599386644"],
    })

    def reject_before_write(**_kwargs):
        assert target.read_text() == "DISCORD_BOT_TOKEN=previous\n"
        raise ValueError("active gateway requires the separate rotation workflow")

    with pytest.raises(ValueError, match="rotation workflow"):
        installer.install_token(
            "submitted-secret",
            target,
            expected_guild="1541131439599386644",
            expected_application="1542135948475637861",
            allowed_root=profile,
            home_channel="1542137541572956193",
            profile_id="nutrition-os",
            expected_os_id="nutrition-os",
            expected_os_version="0.3.0",
            preflight=reject_before_write,
        )
    assert target.read_text() == "DISCORD_BOT_TOKEN=previous\n"


def test_outer_rollback_never_hides_a_possibly_active_submitted_token(tmp_path, monkeypatch):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    (profile / "distribution.yaml").write_text("owner_environment: private\nprofile_id: nutrition-os\nos_id: nutrition-os\nversion: 0.3.0\n")
    target = profile / ".env"
    target.write_text("DISCORD_BOT_TOKEN=previous\n")
    monkeypatch.setattr(installer, "validate_discord_token", lambda _secret: {
        "id": "1542135948475637861", "username": "Nutrition OS",
        "application_id": "1542135948475637861", "guilds": ["1541131439599386644"],
    })
    def fail_after_write(**_kwargs):
        assert "submitted-secret" in target.read_text()
        raise RuntimeError("became active")
    def uncertain(**_kwargs):
        raise RuntimeError("submitted credential may be active")
    with pytest.raises(installer.CredentialActivationUncertain):
        installer.install_token(
            "submitted-secret", target,
            expected_guild="1541131439599386644",
            expected_application="1542135948475637861",
            allowed_root=profile, home_channel="1542137541572956193",
            profile_id="nutrition-os", expected_os_id="nutrition-os", expected_os_version="0.3.0",
            preflight=lambda **_kwargs: None,
            finalizer=fail_after_write, rollback_guard=uncertain,
        )
    assert "submitted-secret" in target.read_text()


def test_transitional_unit_file_states_are_unknown(monkeypatch):
    def completed(state):
        return subprocess.CompletedProcess(
            [], 0,
            f"LoadState=loaded\nActiveState=inactive\nUnitFileState={state}\nFragmentPath=/tmp/unit\n",
            "",
        )
    for state in ("enabling", "disabling", ""):
        monkeypatch.setattr(installer.subprocess, "run", lambda *_args, _state=state, **_kwargs: completed(_state))
        assert installer._service_state("unit.service")["known"] is False


def test_unknown_service_state_and_live_prior_pid_fail_closed(tmp_path):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    common = dict(
        profile_id="nutrition-os",
        home_channel="1542137541572956193",
        application_id="1542135948475637861",
        guild_id="1541131439599386644",
        service_config_root=tmp_path / ".config/systemd/user",
        canonical_profiles_root=profile.parent,
    )
    with pytest.raises(RuntimeError, match="service state"):
        installer.finalize_profile(
            profile,
            service_state_reader=lambda _unit: {"known": False},
            **common,
        )
    with pytest.raises(ValueError, match="rotation workflow"):
        installer.finalize_profile(
            profile,
            service_state_reader=lambda _unit: {"known": True, "load_state": "not-found", "active_state": "inactive", "unit_file_state": "", "active": False, "enabled": False, "unit_path": None},
            state_reader=lambda _path: {"pid": 77},
            process_alive=lambda pid, _profile: pid == 77,
            **common,
        )


def test_malformed_gateway_state_is_never_quiescent(tmp_path):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    (profile / "gateway_state.json").write_text("not-json")
    service = {
        "known": True, "load_state": "not-found", "active_state": "inactive",
        "unit_file_state": "", "active": False, "enabled": False, "unit_path": None,
    }
    with pytest.raises(RuntimeError, match="may still be active"):
        installer.ensure_profile_quiescent(
            profile, profile_id="nutrition-os",
            service_state_reader=lambda _unit: service,
        )


def test_failed_finalization_stops_service_and_restores_config_and_dropin(tmp_path):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    config = profile / "config.yaml"
    config.write_text("before: true\n")
    receipt = profile / "discord-install-receipt.json"
    receipt.write_text('{"old":true}\n')
    service_root = tmp_path / ".config/systemd/user"
    dropin = service_root / "hermes-gateway-nutrition-os.service.d/30-station-runtime.conf"
    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        if "platforms.discord.enabled" in command:
            config.write_text("mutated: true\n")
        if command[-1] == "doctor":
            return subprocess.CompletedProcess(command, 1, "", "doctor failed")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    with pytest.raises(installer.CredentialActivationUncertain, match="activation cannot be disproved"):
        installer.finalize_profile(
            profile,
            profile_id="nutrition-os",
            home_channel="1542137541572956193",
            application_id="1542135948475637861",
            guild_id="1541131439599386644",
            runner=run,
            service_state_reader=lambda _unit: {"known": True, "load_state": "not-found", "active_state": "inactive", "unit_file_state": "", "active": False, "enabled": False, "unit_path": None},
            service_config_root=service_root,
            canonical_profiles_root=profile.parent,
        )

    assert config.read_text() == "before: true\n"
    assert receipt.read_text() == '{"old":true}\n'
    assert not dropin.exists()
    assert ["systemctl", "--user", "disable", "--now", "hermes-gateway-nutrition-os.service"] in calls
    assert ["systemctl", "--user", "daemon-reload"] in calls


def test_preexisting_fragment_path_is_rejected_without_mutation(tmp_path):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    custom_unit = tmp_path / "custom/hermes-gateway-nutrition-os.service"
    custom_unit.parent.mkdir()
    custom_unit.write_text("original-unit\n")
    calls = []

    with pytest.raises(ValueError, match="rotation workflow"):
        installer.finalize_profile(
            profile,
            profile_id="nutrition-os",
            home_channel="1542137541572956193",
            application_id="1542135948475637861",
            guild_id="1541131439599386644",
            runner=lambda command, **_kwargs: calls.append(command),
            service_state_reader=lambda _unit: {
                "known": True, "load_state": "loaded", "active": False,
                "enabled": False, "unit_path": str(custom_unit),
            },
            service_config_root=tmp_path / ".config/systemd/user",
            canonical_profiles_root=profile.parent,
        )
    assert calls == []
    assert custom_unit.read_text() == "original-unit\n"


def test_canonical_unit_file_is_rejected_even_before_daemon_reload(tmp_path):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    service_root = tmp_path / ".config/systemd/user"
    service_root.mkdir(parents=True)
    unit = service_root / "hermes-gateway-nutrition-os.service"
    unit.write_text("preexisting\n")
    with pytest.raises(ValueError, match="rotation workflow"):
        installer.finalize_profile(
            profile,
            profile_id="nutrition-os", home_channel="1542137541572956193",
            application_id="1542135948475637861", guild_id="1541131439599386644",
            service_state_reader=lambda _unit: {
                "known": True, "load_state": "not-found", "active_state": "inactive",
                "unit_file_state": "", "active": False, "enabled": False, "unit_path": None,
            },
            service_config_root=service_root,
            canonical_profiles_root=profile.parent,
        )
    assert unit.read_text() == "preexisting\n"


def test_any_preexisting_dropin_directory_is_rejected(tmp_path):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    service_root = tmp_path / ".config/systemd/user"
    dropins = service_root / "hermes-gateway-nutrition-os.service.d"
    dropins.mkdir(parents=True)
    (dropins / "99-preexisting.conf").write_text("[Service]\nEnvironment=BAD=1\n")
    with pytest.raises(ValueError, match="rotation workflow"):
        installer.finalize_profile(
            profile,
            profile_id="nutrition-os", home_channel="1542137541572956193",
            application_id="1542135948475637861", guild_id="1541131439599386644",
            service_state_reader=lambda _unit: {
                "known": True, "load_state": "not-found", "active_state": "inactive",
                "unit_file_state": "", "active": False, "enabled": False, "unit_path": None,
            },
            service_config_root=service_root,
            canonical_profiles_root=profile.parent,
        )


def test_null_start_time_cannot_produce_receipt(tmp_path):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    (profile / "config.yaml").write_text("before: true\n")
    states = iter([
        {},
        {"gateway_state": "running", "pid": 42, "start_time": None,
         "platforms": {"discord": {"state": "connected", "writer_pid": 42, "writer_start_time": None}}},
    ])
    service = {"known": True, "load_state": "not-found", "active_state": "inactive", "unit_file_state": "", "active": False, "enabled": False, "unit_path": None}
    with pytest.raises(installer.CredentialActivationUncertain, match="activation cannot be disproved"):
        installer.finalize_profile(
            profile,
            profile_id="nutrition-os", home_channel="1542137541572956193",
            application_id="1542135948475637861", guild_id="1541131439599386644",
            runner=lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, "", ""),
            state_reader=lambda _path: next(states), service_state_reader=lambda _unit: service,
            process_alive=lambda _pid, _profile: True, process_start_time=lambda _pid: None,
            state_mtime=lambda _path: 200.0, wall_clock=lambda: 100.0, attempts=1,
            service_config_root=tmp_path / ".config/systemd/user",
            canonical_profiles_root=profile.parent,
        )


def test_rollback_requires_exact_unit_file_state(tmp_path):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    (profile / "config.yaml").write_text("before: true\n")
    states = iter([
        {"known": True, "load_state": "not-found", "active_state": "inactive", "unit_file_state": "", "active": False, "enabled": False, "unit_path": None},
        {"known": True, "load_state": "not-found", "active_state": "inactive", "unit_file_state": "enabled-runtime", "active": False, "enabled": False, "unit_path": None},
    ])
    gateway_states = iter([{}, {"pid": 42, "start_time": 20}])
    def run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1 if command[-1] == "doctor" else 0, "", "")
    with pytest.raises(RuntimeError, match="rollback failed"):
        installer.finalize_profile(
            profile,
            profile_id="nutrition-os", home_channel="1542137541572956193",
            application_id="1542135948475637861", guild_id="1541131439599386644",
            runner=run, service_state_reader=lambda _unit: next(states),
            state_reader=lambda _path: next(gateway_states),
            process_alive=lambda _pid, _profile: False,
            process_start_time=lambda _pid: None,
            service_config_root=tmp_path / ".config/systemd/user",
            canonical_profiles_root=profile.parent,
        )


def test_systemd_tree_rejects_symlinked_ancestors(tmp_path):
    real_config = tmp_path / "real-config"
    real_config.mkdir()
    (tmp_path / ".config").symlink_to(real_config, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe ancestor"):
        installer._validate_owned_systemd_tree(tmp_path / ".config/systemd/user")


def test_file_snapshot_preserves_special_permission_bits(tmp_path):
    path = tmp_path / "state"
    path.write_text("before")
    path.chmod(0o2640)
    snapshot = installer._snapshot_file(path)
    path.write_text("after")
    path.chmod(0o600)
    installer._restore_file(path, snapshot)
    assert path.read_text() == "before"
    assert stat.S_IMODE(path.stat().st_mode) == 0o2640


def test_unreadable_cmdline_never_proves_launched_pid_is_dead(tmp_path):
    profile = tmp_path / ".hermes/profiles/nutrition-os"
    profile.mkdir(parents=True)
    gateway_states = iter([{}, {"pid": 42, "start_time": 99}])
    baseline = {
        "known": True, "load_state": "not-found", "active_state": "inactive",
        "unit_file_state": "", "active": False, "enabled": False, "unit_path": None,
    }

    def run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1 if command[-1] == "doctor" else 0, "", "")

    with pytest.raises(installer.CredentialActivationUncertain, match="activation cannot be disproved"):
        installer.finalize_profile(
            profile,
            profile_id="nutrition-os", home_channel="1542137541572956193",
            application_id="1542135948475637861", guild_id="1541131439599386644",
            runner=run,
            state_reader=lambda _path: next(gateway_states),
            service_state_reader=lambda _unit: baseline,
            process_alive=lambda _pid, _profile: False,
            process_start_time=lambda _pid: 99,
            wait=lambda _seconds: None,
            service_config_root=tmp_path / ".config/systemd/user",
            canonical_profiles_root=profile.parent,
        )
