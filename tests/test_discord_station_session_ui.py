from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "hermes/plugins/platforms/discord/agk_session_control_ui.py"
ADAPTER = ROOT / "hermes/plugins/platforms/discord/adapter.py"


def test_station_session_manager_is_registered_as_native_discord_command():
    adapter = ADAPTER.read_text(encoding="utf-8")
    assert "register_station_session_commands" in adapter
    assert '"station-sessions": 0' in adapter
    assert "station-sessions" in UI.read_text(encoding="utf-8")


def test_station_session_manager_uses_dynamic_discord_components():
    source = UI.read_text(encoding="utf-8")
    for contract in (
        "discord.ui.View",
        "discord.ui.Select",
        "discord.ui.Modal",
        "Refresh",
        "Logs",
        "Prompt",
        "Stop",
        "Archive",
        "Delete",
        "Close",
    ):
        assert contract in source


def test_station_session_manager_rechecks_auth_and_channel_on_callbacks():
    source = UI.read_text(encoding="utf-8")
    assert "_authorized" in source
    assert "channel_allowed" in source
    assert "interaction.user" in source
    assert "interaction.channel_id" in source


def test_station_session_manager_has_pagination_and_destructive_confirmation():
    source = UI.read_text(encoding="utf-8")
    assert "page_size = 25" in source
    assert "Previous" in source
    assert "Next" in source
    assert "confirmation_token" in source
    assert "Confirm" in source
    assert "self.target = parent.selected_target()" in source
    assert "self.target = view.selected_target()" in source


def test_station_session_manager_renders_plan_progress():
    source = UI.read_text(encoding="utf-8")
    assert "progress_label" in source
    assert "Plan progress" in source


def test_station_session_initial_callback_defers_before_catalog_load():
    source = UI.read_text(encoding="utf-8")
    callback = source.split("async def station_sessions", 1)[1]
    assert callback.index("interaction.response.defer") < callback.index("view.load")
