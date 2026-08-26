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


def test_install_includes_the_transactional_client_control_plane():
    source = (ROOT / "install.sh").read_text(encoding="utf-8")
    launcher = (ROOT / "bin" / "agk").read_text(encoding="utf-8")

    assert 'scripts/client_control.py' in source
    assert 'cp -a "$repo_root/client" "$install_root/client"' in source
    assert 'for client_launcher in client-init client-doctor client-status client-env provision-client' in source
    assert 'client)' in launcher
    assert 'scripts/client_control.py' in launcher


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
