import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "bootstrap-macos.sh"


def test_macos_bootstrap_is_valid_and_stays_single_user():
    result = subprocess.run(
        ["bash", "-n", str(BOOTSTRAP)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert "rmux-$rmux_version-macos-$machine.tar.gz" in source
    assert "shasum -a 256 -c -" in source
    assert "cargo build --locked --release" in source
    assert "uv python install 3.12" in source
    assert "install hermes --no-login" in source
    assert "without sudo" in source
    assert "useradd" not in source
    assert "systemctl" not in source
    assert "apt-get" not in source


def test_launchers_derive_their_install_root_from_the_prefix():
    for launcher in (ROOT / "bin/agk", ROOT / "bin/agk-terminal"):
        source = launcher.read_text(encoding="utf-8")
        assert 'launcher=$(resolve_launcher "${BASH_SOURCE[0]}")' in source
        assert 'prefix_root=$(cd "$(dirname "$launcher")/.."' in source
        assert "AGK_TERMINAL_ROOT:-$prefix_root/lib/agk-terminal" in source
