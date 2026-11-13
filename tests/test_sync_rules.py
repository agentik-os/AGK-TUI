"""The managed rule block projected into provider instruction files."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sync_rules", ROOT / "scripts" / "sync-rules.py")
sync_rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync_rules)

RULES = [
    {"id": "a", "title": "Everywhere", "content": "Keep it.", "providers": ["*"]},
    {"id": "b", "title": "Codex only", "content": "Codex.", "providers": ["codex"]},
]
START, END = sync_rules.START, sync_rules.END


def test_only_the_managed_block_is_replaced():
    block = sync_rules.render(RULES, "claude")
    assert "Everywhere" in block and "Codex only" not in block
    assert sync_rules.merge("", block) == block
    mine = "# Mine\n\nmy rule\n"
    synced = sync_rules.merge(mine, block)
    assert synced == f"{mine}\n{block}"
    # Idempotent, and text on both sides of the block survives a change.
    assert sync_rules.merge(synced, block) == synced
    edited = synced + "\nafter the block\n"
    newer = sync_rules.render(RULES, "codex")
    result = sync_rules.merge(edited, newer)
    assert result.startswith(mine) and result.endswith("after the block\n")
    assert "Codex only" in result and result.count(START) == 1


def test_a_marker_left_alone_never_swallows_user_text():
    block = sync_rules.render(RULES, "claude")
    for damaged in (
        f"top\n\n{START}\nold rule\n\nuser text below\n",          # END deleted
        f"top\n{END}\nuser text below\n",                          # START deleted
        f"top\n{END}\nmiddle\n{START}\nuser text below\n",         # reversed
    ):
        result = sync_rules.merge(damaged, block)
        assert "top" in result and "user text below" in result
        assert result.count(START) == 1 and result.count(END) == 1
        assert result.endswith(block)
        assert sync_rules.merge(result, block) == result


def test_no_applicable_rule_removes_the_block_instead_of_leaving_a_header():
    assert sync_rules.render([], "claude") == ""
    synced = sync_rules.merge("mine\n", sync_rules.render(RULES, "claude"))
    assert sync_rules.merge(synced, "") == "mine\n"
    assert sync_rules.merge("", "") == ""


def test_files_keep_their_permissions_and_missing_providers_get_nothing(tmp_path, monkeypatch, capsys):
    rules = tmp_path / "rules.yaml"
    rules.write_text(
        "rules:\n  - {id: a, title: A, enabled: true, providers: ['*'], content: keep}\n"
        "  - {id: off, title: Off, enabled: false, providers: ['*'], content: no}\n",
        encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGK_RULES_CONFIG", str(rules))
    monkeypatch.setattr(sync_rules.shutil, "which", lambda name: None)
    claude = tmp_path / ".claude/CLAUDE.md"
    claude.parent.mkdir()
    claude.write_text("mine\n", encoding="utf-8")
    claude.chmod(0o644)
    # A symlinked file is reported and does not stop the other providers.
    (tmp_path / ".codex").mkdir()
    (tmp_path / "elsewhere.md").write_text("", encoding="utf-8")
    (tmp_path / ".codex/AGENTS.md").symlink_to(tmp_path / "elsewhere.md")

    assert sync_rules.main() == 0
    output = capsys.readouterr()
    assert "## A" in claude.read_text(encoding="utf-8")
    assert "Off" not in claude.read_text(encoding="utf-8")
    assert claude.stat().st_mode & 0o777 == 0o644
    assert "codex: skipped" in output.err
    assert (tmp_path / "elsewhere.md").read_text(encoding="utf-8") == ""
    assert "opencode: not installed, skipped" in output.out
    assert not (tmp_path / ".config").exists()

    assert sync_rules.main() == 0
    assert "(unchanged)" in capsys.readouterr().out
