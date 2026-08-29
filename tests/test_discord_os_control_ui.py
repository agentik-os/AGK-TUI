from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "hermes/plugins/platforms/discord/agk_os_control_ui.py"
ADAPTER = ROOT / "hermes/plugins/platforms/discord/adapter.py"
SPEC = importlib.util.spec_from_file_location("agk_os_control_ui_tested", MODULE)
assert SPEC and SPEC.loader
ui = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ui
SPEC.loader.exec_module(ui)


def record(index: int):
    return ui.OsViewRecord(
        os_id=f"os-{index:02d}", name=f"OS {index:02d}", version="1.0.0",
        owner_environment="private", profile_id=f"os-{index:02d}",
        profile_state="missing", agent_state="declared", discord_mode="disabled",
        discord_state="disabled", doctor_state="blocked",
    )


def test_select_paginates_after_twenty_five_entries():
    view = ui.OsControlView([record(i) for i in range(31)], owner_ids={1})
    select = next(child for child in view.children if isinstance(child, ui.OsSelect))
    assert len(select.options) == 25
    assert view.has_next_page is True
    assert len(view.children) <= 8


def test_compact_copy_contains_current_state_and_no_paths_or_secrets():
    view = ui.OsControlView([record(1)], owner_ids={1})
    content = view.render_content()
    assert "OS 01" in content
    assert "Profile: missing" in content
    assert "Next: Install profile" in content
    assert "/home/" not in content
    assert "TOKEN" not in content.upper()


class Response:
    def __init__(self):
        self.messages = []

    async def send_message(self, content, **kwargs):
        self.messages.append((content, kwargs))

    async def defer(self, **kwargs):
        self.messages.append(("defer", kwargs))

    def is_done(self):
        return bool(self.messages)


class Followup:
    def __init__(self):
        self.messages = []

    async def send(self, content, **kwargs):
        self.messages.append((content, kwargs))


class Interaction:
    def __init__(self, user_id, guild_id=1541131439599386644):
        self.user = type("User", (), {"id": user_id})()
        self.guild_id = guild_id
        self.response = Response()
        self.followup = Followup()


@pytest.mark.asyncio
async def test_every_callback_rechecks_owner_authorization():
    view = ui.OsControlView([record(1)], owner_ids={1})
    interaction = Interaction(2)
    assert await view.interaction_check(interaction) is False
    assert interaction.response.messages == [("Not authorized", {"ephemeral": True})]


@pytest.mark.asyncio
async def test_owner_is_allowed_only_in_exact_agk_guild():
    view = ui.OsControlView([record(1)], owner_ids={1})
    assert await view.interaction_check(Interaction(1)) is True
    wrong_guild = Interaction(1, guild_id=999999999999999999)
    assert await view.interaction_check(wrong_guild) is False
    assert wrong_guild.response.messages[-1] == ("Not authorized", {"ephemeral": True})


class Tree:
    def __init__(self):
        self.commands = []

    def add_command(self, command, override=False):
        self.commands.append((command, override))


class Bot:
    def __init__(self):
        self.tree = Tree()


def test_register_adds_exact_os_application_command():
    bot = Bot()
    ui.register_os_control_center(bot, lambda: [record(1)], owner_ids={1})
    assert len(bot.tree.commands) == 1
    command, override = bot.tree.commands[0]
    assert command.name == "os"
    assert override is True


@pytest.mark.asyncio
async def test_initial_os_slash_rejects_before_loading_fleet_snapshot():
    bot = Bot()
    loads = []
    ui.register_os_control_center(
        bot,
        lambda: loads.append("loaded") or [record(1)],
        owner_ids={1},
    )
    command, _override = bot.tree.commands[0]
    interaction = Interaction(2)

    await command.callback(interaction)

    assert loads == []
    assert interaction.response.messages == [("Not authorized", {"ephemeral": True})]


def test_snapshot_loader_ignores_assignment_rows_without_explicit_owner(tmp_path):
    snapshot = tmp_path / "fleet.json"
    snapshot.write_text(__import__("json").dumps({"organisations": {
        "operator": {"os": [{
            "id": "builder-os", "name": "Builder OS", "version": "0.2.0",
            "owner_environment": "operator", "profile_state": "ready", "agent_state": "ready",
        }]},
        "private": {"os": [
            {"id": "builder-os", "name": "Builder OS", "version": "0.2.0", "assigned": True},
            {"id": "mindset-os", "name": "Mindset OS", "version": "0.3.0",
             "owner_environment": "private", "profile_state": "ready", "agent_state": "ready"},
        ]},
    }}))

    rows = ui.records_from_snapshot(snapshot)

    assert [(row.os_id, row.owner_environment) for row in rows] == [
        ("builder-os", "operator"), ("mindset-os", "private"),
    ]


def test_private_secure_input_installer_is_owner_scoped_and_application_bound(tmp_path):
    row = ui.OsViewRecord(
        os_id="nutrition-os", name="Nutrition OS", version="0.3.0",
        owner_environment="private", profile_id="nutrition-os", profile_state="ready",
        agent_state="ready", discord_mode="dedicated", discord_state="owner-prerequisite",
        doctor_state="ready",
    )

    argv = ui.secure_input_installer_argv(
        row, "1542135948475637861", "1542137541572956193",
        record_validator=lambda _row: Path("/home/private/.hermes/profiles/nutrition-os"),
    )

    assert argv[:2] == ["/usr/bin/env", "-i"]
    assert "HOME=/home/private" in argv
    assert "HERMES_HOME=/home/private/.hermes" in argv
    assert "XDG_RUNTIME_DIR=/run/user/1003" in argv
    assert "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1003/bus" in argv
    assert "--target" in argv
    assert "/home/private/.hermes/profiles/nutrition-os/.env" in argv
    assert argv[argv.index("--expected-os-id") + 1] == "nutrition-os"
    assert argv[argv.index("--expected-os-version") + 1] == "0.3.0"
    assert argv[argv.index("--profile-id") + 1] == "nutrition-os"
    assert argv[argv.index("--home-channel") + 1] == "1542137541572956193"

    operator_row = ui.OsViewRecord(
        os_id="builder-os", name="Builder OS", version="0.2.0",
        owner_environment="operator", profile_id="builder-os", profile_state="ready",
        agent_state="ready", discord_mode="dedicated", discord_state="owner-prerequisite",
        doctor_state="ready",
    )
    with pytest.raises(ValueError, match="Private-owned"):
        ui.secure_input_installer_argv(
            operator_row, "1542135948475637861", "1542137541572956193"
        )


def test_public_application_state_persists_only_public_ids(tmp_path):
    path = tmp_path / "state.json"
    ui.persist_application_id(path, "nutrition-os", "1542135948475637861")
    payload = __import__("json").loads(path.read_text())
    assert payload == {"applications": {"nutrition-os": "1542135948475637861"}, "schema": "agk.os-control-public.v1"}
    assert path.stat().st_mode & 0o777 == 0o600
    assert "token" not in path.read_text().lower()


@pytest.mark.asyncio
async def test_dedicated_bot_absent_returns_locked_oauth_url(tmp_path):
    row = ui.OsViewRecord(
        os_id="nutrition-os", name="Nutrition OS", version="0.3.0",
        owner_environment="private", profile_id="nutrition-os", profile_state="ready",
        agent_state="ready", discord_mode="dedicated", discord_state="owner-prerequisite",
        doctor_state="ready",
    )

    async def missing(_interaction, _application_id):
        assert _interaction.response.is_done()
        return False

    view = ui.OsControlView(
        [row], owner_ids={1}, state_path=tmp_path / "state.json", membership_checker=missing,
        record_validator=lambda _row: Path("/home/private/.hermes/profiles/nutrition-os"),
    )
    interaction = Interaction(1)
    await view.complete_discord_setup(interaction, "1542135948475637861")

    assert interaction.response.messages[0] == ("defer", {"ephemeral": True})
    content, kwargs = interaction.followup.messages[-1]
    assert "https://discord.com/oauth2/authorize?" in content
    assert "guild_id=1541131439599386644" in content
    assert "client_id=1542135948475637861" in content
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_non_private_os_is_rejected_before_public_state_or_discord_lookup(tmp_path):
    row = ui.OsViewRecord(
        os_id="builder-os", name="Builder OS", version="0.2.0",
        owner_environment="operator", profile_id="builder-os", profile_state="ready",
        agent_state="ready", discord_mode="dedicated", discord_state="owner-prerequisite",
        doctor_state="ready",
    )
    async def forbidden_lookup(*_args):
        raise AssertionError("Discord lookup must not run")
    state_path = tmp_path / "state.json"
    view = ui.OsControlView(
        [row], owner_ids={1}, state_path=state_path,
        membership_checker=forbidden_lookup,
    )
    interaction = Interaction(1)
    await view.complete_discord_setup(interaction, "1542135948475637861")
    assert not state_path.exists()
    assert "Private-owned" in interaction.response.messages[-1][0]


@pytest.mark.asyncio
async def test_dedicated_bot_member_starts_https_secure_input(tmp_path):
    row = ui.OsViewRecord(
        os_id="nutrition-os", name="Nutrition OS", version="0.3.0",
        owner_environment="private", profile_id="nutrition-os", profile_state="ready",
        agent_state="ready", discord_mode="dedicated", discord_state="owner-prerequisite",
        doctor_state="ready",
    )
    captured = []

    async def present(_interaction, _application_id):
        assert _interaction.response.is_done()
        return True

    async def launch(argv):
        captured.append(argv)
        return "https://agk-core.tail.example/one-time"

    view = ui.OsControlView(
        [row], owner_ids={1}, state_path=tmp_path / "state.json",
        membership_checker=present, route_launcher=launch,
        channel_resolver=lambda _os_id: "1542137541572956193",
        record_validator=lambda _row: Path("/home/private/.hermes/profiles/nutrition-os"),
    )
    interaction = Interaction(1)
    await view.complete_discord_setup(interaction, "1542135948475637861")

    assert captured
    command = captured[0]
    assert command[command.index("--expected-application") + 1] == "1542135948475637861"
    assert command[command.index("--expected-os-id") + 1] == "nutrition-os"
    assert command[command.index("--expected-os-version") + 1] == "0.3.0"
    assert interaction.response.messages[0] == ("defer", {"ephemeral": True})
    content, kwargs = interaction.followup.messages[-1]
    assert content == "Secure Input ready: https://agk-core.tail.example/one-time"
    assert kwargs["ephemeral"] is True


def test_home_channel_resolves_only_exact_registered_os(tmp_path):
    registry = tmp_path / "os-discord-channels.json"
    registry.write_text(__import__("json").dumps({
        "channels": {
            "nutrition-os": {"id": "1542137541572956193"},
            "unsafe": {"id": "../escape"},
        }
    }))

    assert ui.load_home_channel(registry, "nutrition-os") == "1542137541572956193"
    with pytest.raises(ValueError, match="home channel"):
        ui.load_home_channel(registry, "unsafe")


def test_private_os_record_matches_distribution_identity_and_version(tmp_path):
    root = tmp_path / "profiles"
    profile = root / "nutrition-os"
    profile.mkdir(parents=True)
    (profile / "distribution.yaml").write_text(
        "owner_environment: private\nprofile_id: nutrition-os\nos_id: nutrition-os\nversion: 0.3.0\n"
    )
    row = ui.OsViewRecord(
        os_id="nutrition-os", name="Nutrition OS", version="0.3.0",
        owner_environment="private", profile_id="nutrition-os", profile_state="ready",
        agent_state="ready", discord_mode="dedicated", discord_state="owner-prerequisite",
        doctor_state="ready",
    )
    assert ui.validate_private_os_record(row, root) == profile
    bad = ui.OsViewRecord(**{**row.__dict__, "version": "9.9.9"})
    with pytest.raises(ValueError, match="does not match"):
        ui.validate_private_os_record(bad, root)
    traversal = ui.OsViewRecord(**{**row.__dict__, "os_id": "../escape", "profile_id": "../escape"})
    with pytest.raises(ValueError, match="canonical Private-owned"):
        ui.validate_private_os_record(traversal, root)


def test_station_command_ownership_is_profile_specific():
    operator = ui.station_ui_command_names(Path("/home/operator/.hermes"))
    private = ui.station_ui_command_names(Path("/home/private/.hermes"))
    nutrition = ui.station_ui_command_names(
        Path("/home/private/.hermes/profiles/nutrition-os")
    )
    wrong_owner_nutrition = ui.station_ui_command_names(
        Path("/home/operator/.hermes/profiles/nutrition-os")
    )

    assert "station-sessions" in operator
    assert {"os", "nutrition", "food"}.isdisjoint(operator)
    assert "os" in private
    assert {"nutrition", "food", "station-sessions"}.isdisjoint(private)
    assert {"nutrition", "food"} <= nutrition
    assert {"os", "station-sessions"}.isdisjoint(nutrition)
    assert {"nutrition", "food"}.isdisjoint(wrong_owner_nutrition)


def test_private_os_control_uses_private_and_public_fleet_paths():
    view = ui.OsControlView([], owner_ids={1})
    assert view.state_path == Path("/home/private/.hermes/os-control-state.json")
    source = MODULE.read_text(encoding="utf-8")
    assert '/var/lib/agk-terminal/fleet/os-discord-channels.json' in source
    assert '/home/operator/.hermes/os-discord-channels.json' not in source


def test_os_control_center_registers_only_on_private_gateway():
    source = ADAPTER.read_text(encoding="utf-8")
    assert 'hermes_home == _Path("/home/private/.hermes")' in source
    assert 'hermes_home == _Path("/home/operator/.hermes")' not in source
    slash_start = source.index("def _register_slash_commands")
    registration = source.index("register_os_control_center(", slash_start)
    ui_filter = source.index("if ui_only:", slash_start)
    assert slash_start < registration < ui_filter
    registration_block = source[registration:registration + 500]
    assert 'self.config.extra.get("allow_admin_from")' in source[slash_start:registration + 500]
    assert "_allowed_user_ids" not in registration_block
    assert "hermes_home = self._hermes_home" in source


@pytest.mark.asyncio
async def test_route_launcher_cleans_up_child_on_ready_timeout(monkeypatch):
    class Stdout:
        async def readline(self):
            return b""

    class Process:
        def __init__(self):
            self.stdout = Stdout()
            self.terminated = False
            self.waited = False

        def terminate(self):
            self.terminated = True

        async def wait(self):
            self.waited = True
            return 0

    process = Process()

    async def create(*_args, **_kwargs):
        return process

    async def timeout(_awaitable, timeout):
        assert timeout == 20
        _awaitable.close()
        raise __import__("asyncio").TimeoutError

    monkeypatch.setattr(ui.asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(ui.asyncio, "wait_for", timeout)

    with pytest.raises(__import__("asyncio").TimeoutError):
        await ui._default_route_launcher(["/bin/false"])

    assert process.terminated is True
    assert process.waited is True
