from pathlib import Path


ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "scripts" / "test.sh"


def test_full_test_runner_declares_account_control_runtime_dependencies():
    script = RUNNER.read_text(encoding="utf-8")

    assert "pytest-asyncio" in script
    assert "httpx" in script
    assert "discord.py" in script
    assert "/opt/agk-terminal/hermes-agent" in script
    assert "PYTHONPATH" in script
