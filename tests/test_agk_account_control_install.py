from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATION_OVERLAY = Path("/home/operator/src/Station/overlay")
ACCOUNT_MODULES = (
    "agk_account_control.py",
    "agk_account_control_ui.py",
    "agk_account_oauth.py",
    "agk_account_transactions.py",
    "agk_account_usage_monitor.py",
)


def _bootstrap_source() -> str:
    return "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in ("scripts/sync-hermes.sh", "install.sh")
    )


def test_future_install_enables_private_account_control_center_once():
    source = _bootstrap_source()
    expected = {
        "platforms.discord.extra.account_control_enabled": "true",
        "platforms.discord.extra.account_control_category_id": "1542505218569150585",
        "platforms.discord.extra.account_control_owner_user_id": "1441423462492016821",
        "platforms.discord.extra.account_control_channel_name": "account-control",
        "platforms.discord.extra.account_control_oauth_timeout_seconds": "900",
    }
    for key, value in expected.items():
        command = f"hermes config set {key} {value}"
        assert source.count(command) == 1
    assert "config.yaml" not in "\n".join(
        line for line in source.splitlines() if "account_control_" in line
    )
    assert ".env" not in "\n".join(
        line for line in source.splitlines() if "account_control_" in line
    )


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


def test_install_and_overlay_include_every_account_control_module_and_runner_once():
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    runner = "scripts/agk_provider_oauth_runner.py"
    assert install.count(f'$repo_root/{runner}') == 1
    assert install.count(f'$install_root/{runner}') == 1

    for name in ACCOUNT_MODULES:
        canonical = ROOT / "hermes/plugins/platforms/discord" / name
        mirrored = STATION_OVERLAY / "hermes/plugins/platforms/discord" / name
        assert canonical.is_file(), name
        assert mirrored.read_bytes() == canonical.read_bytes(), name

    canonical_runner = ROOT / runner
    mirrored_runner = STATION_OVERLAY / runner
    assert mirrored_runner.read_bytes() == canonical_runner.read_bytes()


def test_bootstrap_mirrors_include_account_config_without_duplicates():
    for root in (ROOT, STATION_OVERLAY):
        sync = (root / "scripts/sync-hermes.sh").read_text(encoding="utf-8")
        assert sync.count(
            "hermes config set platforms.discord.extra.account_control_enabled true"
        ) == 1
        assert sync.count(
            "hermes config set platforms.discord.extra.account_control_category_id 1542505218569150585"
        ) == 1
        install = (root / "install.sh").read_text(encoding="utf-8")
        assert install.count('$repo_root/scripts/agk_provider_oauth_runner.py') == 1
        assert install.count('$install_root/scripts/agk_provider_oauth_runner.py') == 1
