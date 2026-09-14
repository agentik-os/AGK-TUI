from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_installer_uses_a_published_rmux_release_and_checks_wire_compatibility():
    source = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "RMUX_VERSION:-0.10.0" in source
    assert "rmux_works_for_target" in source
    assert "list-sessions" in source
    assert ".agk-incompatible" in source
    assert "CARGO_TARGET_DIR" in source


def test_fresh_bootstrap_installs_optional_providers_without_blocking_on_login():
    source = (ROOT / "bootstrap-vps.sh").read_text(encoding="utf-8")

    assert 'install "$provider" --no-login' in source
    assert "agk client bootstrap --upgrade" in source
    assert "0 clients provisioned" in source


def test_system_install_preserves_the_collective_mission_context():
    source = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "/home/mission/.hermes/profiles/collective" in source
    assert "HERMES_HOME=/home/mission/.hermes/profiles/collective" in source


def test_install_enables_quiet_gateway_health_monitoring_for_every_profile():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    sync = (ROOT / "scripts" / "sync-hermes.sh").read_text(encoding="utf-8")
    service = (
        ROOT / "systemd" / "agk-gateway-watchdog.service"
    ).read_text(encoding="utf-8")
    timer = (
        ROOT / "systemd" / "agk-gateway-watchdog.timer"
    ).read_text(encoding="utf-8")

    assert "gateway_watchdog.py" in installer
    assert "enable --now agk-gateway-watchdog.timer" in installer
    assert "platforms.discord.gateway_restart_notification false" in sync
    assert "platforms.telegram.gateway_restart_notification false" in sync
    assert "platforms.discord.extra.command_ui_mode ui_only" in sync
    assert "DISCORD_ALLOWED_USERS=" in sync
    assert "platforms.discord.extra.allow_admin_from" in sync
    assert "platforms.discord.extra.group_allow_admin_from" in sync
    assert "ReadWritePaths=/var/lib/agk-terminal" in service
    assert "OnUnitActiveSec=60s" in timer


def test_install_includes_the_transactional_client_control_plane():
    source = (ROOT / "install.sh").read_text(encoding="utf-8")
    launcher = (ROOT / "bin" / "agk").read_text(encoding="utf-8")

    assert 'scripts/client_control.py' in source
    assert 'cp -a "$repo_root/client" "$install_root/client"' in source
    assert 'for client_launcher in client-init client-doctor client-status client-env provision-client' in source
    assert 'client)' in launcher
    assert 'scripts/client_control.py' in launcher


def test_install_reconciles_all_python_requirements_on_upgrade():
    source = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert 'if ! "$install_root/venv/bin/python" -c \'import yaml\'' not in source
    assert '"$install_root/venv/bin/python" -m pip install --disable-pip-version-check' in source
    assert '-r "$repo_root/requirements.txt"' in source


def test_shared_hermes_install_can_pin_and_verify_an_official_commit():
    source = (ROOT / "scripts" / "install-shared-hermes.sh").read_text(
        encoding="utf-8"
    )

    assert "HERMES_OFFICIAL_COMMIT" in source
    assert '--commit "$official_commit" --force-commit' in source
    assert 'installed_commit=$(git -c safe.directory="$official_dir"' in source
    assert '[ "$installed_commit" = "$official_commit" ]' in source
    assert "-name '.hermes-*' -print0" in source
    assert '"$backup_dir/official-runtime.before"' in source
    assert "npm ci --include=dev" in source
    assert "npm ci --workspace web" not in source


def test_install_packages_os_control_center_and_builder_runtime_contract():
    source = (ROOT / "install.sh").read_text(encoding="utf-8")

    for asset in (
        "os_profile_migration.py",
        "install_core_os_packages.py",
        "tailnet_secure_input.py",
        "install-discord-token.py",
        'cp -a "$repo_root/os-packages" "$install_root/os-packages"',
        'cp -a "$repo_root/hermes/plugins/platforms/discord"',
    ):
        assert asset in source
    assert (ROOT / "hermes/plugins/platforms/discord/agk_os_control.py").is_file()
    assert (ROOT / "hermes/plugins/platforms/discord/agk_os_control_ui.py").is_file()
    manifest = (ROOT / "os-packages/builder-os/manifest.yaml").read_text()
    assert "version: 0.2.0" in manifest
    assert "runtime_contract:" in manifest
