from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
OVERLAY_ENV = "AGK_TASK5_STATION_OVERLAY"
FIXTURE_OVERLAY = ROOT / "tests/fixtures/station-task5-overlay"
NEW_ACCOUNT_MODULES = (
    "agk_account_control.py",
    "agk_account_control_ui.py",
    "agk_account_oauth.py",
    "agk_account_transactions.py",
)
EXISTING_ACCOUNT_FILES = (
    "install.sh",
    "scripts/sync-hermes.sh",
    "hermes/plugins/platforms/discord/adapter.py",
    "hermes/plugins/platforms/discord/agk_account_usage_monitor.py",
)
ACCOUNT_SETTINGS = {
    "platforms.discord.extra.account_control_enabled": "true",
    "platforms.discord.extra.account_control_category_id": "1542505218569150585",
    "platforms.discord.extra.account_control_owner_user_id": "1441423462492016821",
    "platforms.discord.extra.account_control_channel_name": "account-control",
    "platforms.discord.extra.account_control_oauth_timeout_seconds": "900",
}


@pytest.fixture
def station_overlay(tmp_path: Path) -> Path:
    """Use an injected real overlay, or a repository fixture in hermetic runs."""
    injected = os.environ.get(OVERLAY_ENV)
    if injected:
        overlay = Path(injected)
        assert overlay.is_dir(), f"{OVERLAY_ENV} does not name an overlay directory"
        return overlay

    overlay = tmp_path / "overlay"
    shutil.copytree(FIXTURE_OVERLAY, overlay)
    discord_dir = overlay / "hermes/plugins/platforms/discord"
    discord_dir.mkdir(parents=True, exist_ok=True)
    canonical_discord = ROOT / "hermes/plugins/platforms/discord"
    for name in NEW_ACCOUNT_MODULES:
        shutil.copy2(canonical_discord / name, discord_dir / name)
    runner = Path("scripts/agk_provider_oauth_runner.py")
    (overlay / runner).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / runner, overlay / runner)
    return overlay


def _bootstrap_source(root: Path = ROOT) -> str:
    return "\n".join(
        (root / path).read_text(encoding="utf-8")
        for path in ("scripts/sync-hermes.sh", "install.sh")
    )


def test_future_install_enables_private_account_control_center_once():
    source = _bootstrap_source()
    for key, value in ACCOUNT_SETTINGS.items():
        assert source.count(f"hermes config set {key} {value}") == 1
    account_lines = "\n".join(
        line for line in source.splitlines() if "account_control_" in line
    )
    assert "config.yaml" not in account_lines
    assert ".env" not in account_lines


def test_legacy_text_channels_are_not_auto_created_or_configured():
    monitor = (
        ROOT / "hermes/plugins/platforms/discord/agk_account_usage_monitor.py"
    ).read_text(encoding="utf-8")
    bootstrap = _bootstrap_source()
    assert "create_text_channel" not in monitor
    assert "_find_or_create_claude_channel" not in monitor
    assert "_summary_channel" not in monitor
    assert "claudecode-all-accounts" not in monitor
    assert "station-account-capacity" not in monitor
    assert "usage_monitor_claude_channel" not in bootstrap
    assert "1542558179899080714" not in bootstrap
    assert "1542558178913550448" not in bootstrap


def test_install_contract_includes_runner_and_atomic_discord_tree():
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    runner = "scripts/agk_provider_oauth_runner.py"
    assert install.count(f"$repo_root/{runner}") == 1
    assert install.count(f"$install_root/{runner}") == 1
    assert 'cp -a "$repo_root/hermes/plugins/platforms/discord"' in install
    for name in (*NEW_ACCOUNT_MODULES, "agk_account_usage_monitor.py"):
        assert (ROOT / "hermes/plugins/platforms/discord" / name).is_file(), name


def test_overlay_new_dedicated_artifacts_are_byte_identical(station_overlay: Path):
    canonical_discord = ROOT / "hermes/plugins/platforms/discord"
    overlay_discord = station_overlay / "hermes/plugins/platforms/discord"
    for name in NEW_ACCOUNT_MODULES:
        assert (overlay_discord / name).read_bytes() == (canonical_discord / name).read_bytes(), name
    runner = Path("scripts/agk_provider_oauth_runner.py")
    assert (station_overlay / runner).read_bytes() == (ROOT / runner).read_bytes()


def test_overlay_existing_files_contain_only_scoped_account_contract(station_overlay: Path):
    sync = (station_overlay / "scripts/sync-hermes.sh").read_text(encoding="utf-8")
    install = (station_overlay / "install.sh").read_text(encoding="utf-8")
    adapter = (
        station_overlay / "hermes/plugins/platforms/discord/adapter.py"
    ).read_text(encoding="utf-8")
    monitor = (
        station_overlay / "hermes/plugins/platforms/discord/agk_account_usage_monitor.py"
    ).read_text(encoding="utf-8")

    for key, value in ACCOUNT_SETTINGS.items():
        assert sync.count(f"hermes config set {key} {value}") == 1
    assert install.count("$repo_root/scripts/agk_provider_oauth_runner.py") == 1
    assert install.count("$install_root/scripts/agk_provider_oauth_runner.py") == 1
    for marker in (
        "register_account_control_center",
        "reconcile_account_control_channel",
        "refresh_account_surfaces",
        "DiscordAccountUsageMonitor",
    ):
        assert marker in adapter
    for forbidden in (
        "create_text_channel",
        "_find_or_create_claude_channel",
        "_summary_channel",
        "claudecode-all-accounts",
        "station-account-capacity",
    ):
        assert forbidden not in monitor


def test_overlay_preserves_critical_station_capabilities(station_overlay: Path):
    install = (station_overlay / "install.sh").read_text(encoding="utf-8")
    sync = (station_overlay / "scripts/sync-hermes.sh").read_text(encoding="utf-8")
    adapter = (
        station_overlay / "hermes/plugins/platforms/discord/adapter.py"
    ).read_text(encoding="utf-8")

    for marker in (
        "configure-station-discord-interagent.py",
        "station_safe_gateway_reload.py",
        "tailnet_secure_input.py",
        "completion_harness.py",
        "recovery_auditor.py",
        "fleet_recovery_auditor.py",
        "recovery_router.py",
        "completion_oracle_gate.py",
        "approval_gate.py",
        "agk_discord_ui_policy",
        'cp -a "$repo_root/hermes/agents" "$install_root/agents"',
        "agk-recovery-auditor.service",
        "agk-recovery-auditor.timer",
        "/var/lib/station/recovery/approvals",
        "/var/lib/station/recovery/oracle",
        "systemctl enable --now agk-recovery-auditor.timer",
    ):
        assert marker in install
    for marker in (
        "agk_discord_ui_policy",
        'for agent_source in "$agent_source_root"/*',
        "agk-discord-ui-policy",
    ):
        assert marker in sync
    for marker in (
        "normalize_station_reply",
        "register_recovery_commands",
        '"station-recovery"',
        '"recap"',
    ):
        assert marker in adapter
