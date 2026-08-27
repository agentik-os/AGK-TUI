import hashlib
import importlib.util
import json
import stat
import sys
import threading
from collections import Counter
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "hermes/plugins/platforms/discord/agk_account_transactions.py"
ACCOUNT_CONTROL_MODULE = ROOT / "hermes/plugins/platforms/discord/agk_account_control.py"


def load_transactions():
    assert MODULE.exists(), "transaction coordinator does not exist"
    spec = importlib.util.spec_from_file_location("agk_account_transactions", MODULE)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def load_account_control():
    assert ACCOUNT_CONTROL_MODULE.exists(), "account control module does not exist"
    spec = importlib.util.spec_from_file_location("agk_account_control_for_transactions", ACCOUNT_CONTROL_MODULE)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    existing_usage = sys.modules.get("agent.account_usage")
    if existing_usage is None:
        usage_stub = ModuleType("agent.account_usage")
        usage_stub.__dict__["fetch_account_usage"] = lambda *args, **kwargs: None
        sys.modules["agent.account_usage"] = usage_stub
    try:
        spec.loader.exec_module(loaded)
    finally:
        if existing_usage is None:
            sys.modules.pop("agent.account_usage", None)
    return loaded


class FakeStore:
    def __init__(self, home: Path, attempt):
        self.path = home / "state/account-oauth/attempts.json"
        self.attempt = attempt

    def get(self, attempt_id):
        return self.attempt if attempt_id == self.attempt.attempt_id else None


class FakeAliasRegistry:
    def __init__(self, path: Path, events: list[str]):
        self.path = path
        self.events = events
        self.values = {"openai-codex": {"old123": "Agentik", "keep456": "Simono"}}
        self.fail_bind = False
        self.fail_replace = False

    def snapshot(self):
        return {provider: dict(rows) for provider, rows in self.values.items()}

    def replace(self, values):
        if self.fail_replace:
            raise OSError("registry restore failed")
        self.values = {provider: dict(rows) for provider, rows in values.items()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.values), encoding="utf-8")
        self.path.chmod(0o600)

    def bind(self, provider, owner_name, credential_id):
        self.events.append("bind-nickname")
        if self.fail_bind:
            raise OSError("registry write failed")
        rows = self.values.setdefault(provider, {})
        rows = {key: value for key, value in rows.items() if value.casefold() != owner_name.casefold()}
        rows[credential_id] = owner_name
        self.values[provider] = rows


class Fakes:
    def __init__(self, tmp_path: Path, *, operation="reconnect"):
        self.events = []
        self.probe_ok = True
        self.remove_old_ok = True
        self.remove_candidate_ok = True
        self.refresh_ok = True
        self.artifact_remover = lambda path: path.unlink(missing_ok=True)
        self.pool_ids = ["old123", "keep456", "new789"]
        self.before_ids = ["old123", "keep456"]
        self.attempt = SimpleNamespace(
            attempt_id="attempt-1",
            provider="openai-codex",
            operation=operation,
            owner_name="Agentik",
            target_credential_id="old123" if operation == "reconnect" else None,
            status="succeeded",
        )
        self.store = FakeStore(tmp_path, self.attempt)
        self.registry = FakeAliasRegistry(tmp_path / "provider-account-aliases.json", self.events)
        for name, value in (("auth.json", "private-auth"), ("config.yaml", "model: test\n")):
            (tmp_path / name).write_text(value, encoding="utf-8")
        self.registry.path.write_text("aliases-before", encoding="utf-8")
        self.registry.path.chmod(0o600)

    def pool_reader(self, provider):
        if "bind-nickname" not in self.events:
            self.events.append("discover-candidate")
        elif "remove-old" not in self.events:
            self.events.append("read-pool")
        else:
            self.events.append("read-final-pool")
        return [SimpleNamespace(id=value) for value in self.pool_ids]

    def probe(self, provider, entry):
        self.events.append("probe-candidate")
        return self.probe_ok

    def usage(self, provider, entry):
        self.events.append("usage-candidate")
        return {"availability": "available"}

    def remove(self, provider, credential_id):
        event = "remove-old" if credential_id == "old123" else "remove-candidate"
        self.events.append(event)
        if credential_id == "old123" and not self.remove_old_ok:
            return False
        if credential_id == "new789" and not self.remove_candidate_ok:
            return False
        self.pool_ids.remove(credential_id)
        return True

    def refresh(self):
        self.events.append("refresh-surfaces")
        if not self.refresh_ok:
            raise RuntimeError("presentation failed")


def coordinator(tmp_path, fakes):
    transactions = load_transactions()
    return transactions.AccountTransactionCoordinator(
        tmp_path,
        fakes.store,
        fakes.registry,
        pool_reader=fakes.pool_reader,
        pre_pool_ids=lambda _attempt: tuple(fakes.before_ids),
        probe_candidate=fakes.probe,
        fetch_usage=fakes.usage,
        remove_credential=fakes.remove,
        refresh_surfaces=fakes.refresh,
        backup_observer=lambda: fakes.events.append("backup"),
        artifact_remover=getattr(fakes, "artifact_remover", None),
    )


def test_reconnect_verifies_candidate_before_removing_old(tmp_path):
    fakes = Fakes(tmp_path)

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert fakes.events == [
        "backup", "discover-candidate", "probe-candidate", "usage-candidate",
        "bind-nickname", "read-pool", "remove-old", "read-final-pool", "refresh-surfaces",
    ]
    assert result.status == "committed"
    assert result.old_credential_id == "old123"
    assert result.new_credential_id == "new789"


def test_failed_candidate_probe_preserves_old_credential(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.probe_ok = False

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert "remove-old" not in fakes.events
    assert "old123" in fakes.pool_ids
    assert result.status == "rolled_back"


def test_backup_is_private_complete_and_checksummed_before_discovery(tmp_path):
    fakes = Fakes(tmp_path)

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "committed"
    backups = list((tmp_path / "state/account-transactions/backups").iterdir())
    assert len(backups) == 1
    backup = backups[0]
    assert stat.S_IMODE(backup.stat().st_mode) == 0o700
    manifest_path = backup / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["sha256"]
    assert set(manifest) == {"auth.json", "config.yaml", "provider-account-aliases.json"}
    for name, digest in manifest.items():
        copied = backup / name
        assert stat.S_IMODE(copied.stat().st_mode) == 0o600
        assert hashlib.sha256(copied.read_bytes()).hexdigest() == digest
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600


def test_production_alias_registry_bind_uses_atomic_private_replace_and_readback(
    tmp_path, monkeypatch
):
    account_control = load_account_control()
    path = tmp_path / "provider-account-aliases.json"
    registry = account_control.AliasRegistry(path)
    registry.bind("openai-codex", "Agentik", "old123")
    before = path.read_bytes()
    observed = []
    real_replace = account_control.os.replace

    def observe_replace(source, destination):
        source = Path(source)
        destination = Path(destination)
        observed.append((source.name, destination))
        assert destination == path
        assert path.read_bytes() == before
        assert stat.S_IMODE(source.stat().st_mode) == 0o600
        payload = json.loads(source.read_text(encoding="utf-8"))
        assert payload["providers"]["openai-codex"] == [
            {"credential_id": "new789", "owner_nickname": "Agentik"}
        ]
        real_replace(source, destination)

    monkeypatch.setattr(account_control.os, "replace", observe_replace)

    registry.bind("openai-codex", "Agentik", "new789")

    assert len(observed) == 1
    assert registry.snapshot() == {"openai-codex": {"new789": "Agentik"}}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob("*.new"))


def test_registry_write_failure_restores_aliases_and_removes_only_candidate(tmp_path):
    fakes = Fakes(tmp_path)
    original = fakes.registry.snapshot()
    fakes.registry.fail_bind = True

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "rolled_back"
    assert fakes.registry.snapshot() == original
    assert "old123" in fakes.pool_ids and "new789" not in fakes.pool_ids
    assert "remove-old" not in fakes.events


def test_candidate_cleanup_failure_requires_reconciliation(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.probe_ok = False
    fakes.remove_candidate_ok = False

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert "new789" in fakes.pool_ids and "old123" in fakes.pool_ids
    assert "remove-old" not in fakes.events


def test_alias_restore_failure_requires_reconciliation_without_removing_old(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.probe_ok = False
    fakes.registry.fail_replace = True

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert "old123" in fakes.pool_ids and "new789" not in fakes.pool_ids
    assert "remove-old" not in fakes.events


def test_old_removal_failure_retains_both_and_never_fabricates_success(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.remove_old_ok = False

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert {"old123", "new789"}.issubset(fakes.pool_ids)
    assert "refresh-surfaces" not in fakes.events


def test_final_pool_read_failure_after_old_removal_never_removes_candidate(tmp_path):
    fakes = Fakes(tmp_path)
    normal_reader = fakes.pool_reader

    def fail_final_read(provider):
        if "remove-old" in fakes.events:
            raise OSError("synthetic final read failure")
        return normal_reader(provider)

    fakes.pool_reader = fail_final_read

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert "new789" in fakes.pool_ids and "old123" not in fakes.pool_ids
    assert "remove-candidate" not in fakes.events
    assert "refresh-surfaces" not in fakes.events


def test_malformed_final_entry_after_old_removal_never_removes_candidate(tmp_path):
    fakes = Fakes(tmp_path)
    normal_reader = fakes.pool_reader

    def malformed_final_pool(provider):
        entries = normal_reader(provider)
        if "remove-old" in fakes.events:
            entries.append(SimpleNamespace(id="malformed id"))
        return entries

    fakes.pool_reader = malformed_final_pool

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert "new789" in fakes.pool_ids and "old123" not in fakes.pool_ids
    assert "remove-candidate" not in fakes.events
    assert "refresh-surfaces" not in fakes.events


def test_old_removal_that_mutates_then_raises_never_removes_candidate(tmp_path):
    fakes = Fakes(tmp_path)

    def partial_remove(provider, credential_id):
        event = "remove-old" if credential_id == "old123" else "remove-candidate"
        fakes.events.append(event)
        fakes.pool_ids.remove(credential_id)
        if credential_id == "old123":
            raise OSError("synthetic post-mutation failure")
        return True

    fakes.remove = partial_remove

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert "new789" in fakes.pool_ids and "old123" not in fakes.pool_ids
    assert "remove-candidate" not in fakes.events
    assert "refresh-surfaces" not in fakes.events


def test_duplicate_candidate_ids_are_not_committed(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.pool_ids.append("new789")

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert "remove-old" not in fakes.events


def test_final_reconciliation_rejects_disappearing_unrelated_baseline_id(tmp_path):
    fakes = Fakes(tmp_path)

    def remove_with_disappearance(provider, credential_id):
        fakes.events.append("remove-old")
        fakes.pool_ids.remove(credential_id)
        fakes.pool_ids.remove("keep456")
        return True

    fakes.remove = remove_with_disappearance

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert "refresh-surfaces" not in fakes.events


def test_final_reconciliation_rejects_rogue_replacement_with_same_count(tmp_path):
    fakes = Fakes(tmp_path)

    def remove_with_rogue_replacement(provider, credential_id):
        fakes.events.append("remove-old")
        fakes.pool_ids.remove(credential_id)
        fakes.pool_ids[fakes.pool_ids.index("keep456")] = "rogue999"
        return True

    fakes.remove = remove_with_rogue_replacement

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert set(fakes.pool_ids) == {"new789", "rogue999"}
    assert "refresh-surfaces" not in fakes.events


def test_final_reconciliation_rejects_duplicate_baseline_replacing_another(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.before_ids.append("base777")
    fakes.pool_ids.insert(2, "base777")

    def remove_with_duplicate_replacement(provider, credential_id):
        fakes.events.append("remove-old")
        fakes.pool_ids.remove(credential_id)
        fakes.pool_ids[fakes.pool_ids.index("base777")] = "keep456"
        return True

    fakes.remove = remove_with_duplicate_replacement

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert Counter(fakes.pool_ids) == Counter({"keep456": 2, "new789": 1})
    assert "refresh-surfaces" not in fakes.events


def test_final_reconciliation_accepts_reordered_exact_multiset(tmp_path):
    fakes = Fakes(tmp_path)

    def remove_and_reorder(provider, credential_id):
        fakes.events.append("remove-old")
        fakes.pool_ids.remove(credential_id)
        fakes.pool_ids.reverse()
        return True

    fakes.remove = remove_and_reorder

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "committed"
    assert fakes.pool_ids == ["new789", "keep456"]


def test_finalize_replay_returns_terminal_outcome_without_mutation(tmp_path):
    fakes = Fakes(tmp_path)
    transaction = coordinator(tmp_path, fakes)

    first = transaction.finalize("attempt-1")
    events_after_first = list(fakes.events)
    second = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert (
        second.status,
        second.provider,
        second.owner_name,
        second.old_credential_id,
        second.new_credential_id,
        second.message,
    ) == (
        first.status,
        first.provider,
        first.owner_name,
        first.old_credential_id,
        first.new_credential_id,
        first.message,
    )
    assert second.status == "committed"
    assert fakes.events == events_after_first
    assert Counter(fakes.pool_ids) == Counter({"keep456": 1, "new789": 1})
    state = json.loads(
        (tmp_path / "state/account-transactions/attempt-1.json").read_text(encoding="utf-8")
    )
    assert state["phase"] == "terminal"
    assert "private-auth" not in json.dumps(state)


def test_irreversible_state_replay_never_reenters_candidate_cleanup(tmp_path):
    fakes = Fakes(tmp_path)
    transaction = coordinator(tmp_path, fakes)

    def fail_terminal_persistence(attempt_id, result):
        raise OSError("synthetic terminal persistence failure")

    transaction._write_terminal_state = fail_terminal_persistence
    first = transaction.finalize("attempt-1")
    events_after_first = list(fakes.events)
    state_path = tmp_path / "state/account-transactions/attempt-1.json"
    irreversible = json.loads(state_path.read_text(encoding="utf-8"))

    second = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert first.status == "reconciliation_required"
    assert irreversible["phase"] == "irreversible"
    assert second.status == "reconciliation_required"
    assert fakes.events == events_after_first
    assert "remove-candidate" not in fakes.events
    assert Counter(fakes.pool_ids) == Counter({"keep456": 1, "new789": 1})


def test_terminal_replay_persistence_failure_is_non_destructive(tmp_path):
    fakes = Fakes(tmp_path)
    first = coordinator(tmp_path, fakes).finalize("attempt-1")
    events_after_first = list(fakes.events)
    replay = coordinator(tmp_path, fakes)

    def fail_terminal_persistence(attempt_id, result):
        raise OSError("synthetic replay persistence failure")

    replay._write_terminal_state = fail_terminal_persistence

    second = replay.finalize("attempt-1")

    assert first.status == "committed"
    assert second.status == "reconciliation_required"
    assert fakes.events == events_after_first
    assert "remove-candidate" not in fakes.events
    assert Counter(fakes.pool_ids) == Counter({"keep456": 1, "new789": 1})


def test_invalid_terminal_state_is_non_destructive_reconciliation(tmp_path):
    fakes = Fakes(tmp_path)
    first = coordinator(tmp_path, fakes).finalize("attempt-1")
    events_after_first = list(fakes.events)
    state_path = tmp_path / "state/account-transactions/attempt-1.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["result"]["status"] = "unknown"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    state_path.chmod(0o600)

    second = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert first.status == "committed"
    assert second.status == "reconciliation_required"
    assert fakes.events == events_after_first
    assert "remove-candidate" not in fakes.events
    assert Counter(fakes.pool_ids) == Counter({"keep456": 1, "new789": 1})


def test_concurrent_finalize_is_serialized_and_removes_old_once(tmp_path):
    fakes = Fakes(tmp_path)
    original_reader = fakes.pool_reader
    discovery_barrier = threading.Barrier(2)

    def synchronized_reader(provider):
        if "bind-nickname" not in fakes.events:
            try:
                discovery_barrier.wait(timeout=0.2)
            except threading.BrokenBarrierError:
                pass
        return original_reader(provider)

    fakes.pool_reader = synchronized_reader
    transactions = [coordinator(tmp_path, fakes), coordinator(tmp_path, fakes)]
    results = []

    threads = [
        threading.Thread(target=lambda item=item: results.append(item.finalize("attempt-1")))
        for item in transactions
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert [result.status for result in results] == ["committed", "committed"]
    assert fakes.events.count("remove-old") == 1
    assert fakes.events.count("remove-candidate") == 0
    assert Counter(fakes.pool_ids) == Counter({"keep456": 1, "new789": 1})


def test_post_commit_refresh_failure_preserves_pool_and_marks_presentation_pending(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.refresh_ok = False

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "presentation_reconciliation_pending"
    assert "new789" in fakes.pool_ids and "old123" not in fakes.pool_ids


def test_add_commits_one_candidate_without_removing_existing_credentials(tmp_path):
    fakes = Fakes(tmp_path, operation="add")
    fakes.attempt.owner_name = "Loumna"

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "committed"
    assert result.old_credential_id is None
    assert set(fakes.pool_ids) == {"old123", "keep456", "new789"}
    assert "remove-old" not in fakes.events


def test_usage_failure_is_recorded_as_unavailable_without_blocking_commit(tmp_path):
    fakes = Fakes(tmp_path)

    def unavailable(provider, entry):
        fakes.events.append("usage-candidate")
        raise RuntimeError("provider usage unavailable")

    fakes.usage = unavailable

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "committed"
    assert "usage unavailable" in result.message.casefold()


def test_terminal_paths_remove_oauth_artifacts_without_retaining_credentials(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.probe_ok = False
    artifacts = [
        fakes.store.path.parent / "attempt-1.fifo",
        fakes.store.path.parent / "attempt-1.result.json",
        fakes.store.path.parent / "attempt-1.result.raw.log",
    ]
    fakes.store.path.parent.mkdir(parents=True, exist_ok=True)
    for artifact in artifacts:
        artifact.write_text("private material", encoding="utf-8")

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "rolled_back"
    assert all(not artifact.exists() for artifact in artifacts)


@pytest.mark.parametrize("suffix", [".fifo", ".result.json", ".result.raw.log"])
def test_oauth_artifact_cleanup_failure_surfaces_security_pending(tmp_path, suffix):
    fakes = Fakes(tmp_path)
    parent = fakes.store.path.parent
    parent.mkdir(parents=True, exist_ok=True)
    artifacts = [parent / f"attempt-1{item}" for item in (".fifo", ".result.json", ".result.raw.log")]
    for artifact in artifacts:
        artifact.write_text("private material", encoding="utf-8")
    blocked = parent / f"attempt-1{suffix}"

    def selective_remover(path):
        if path == blocked:
            raise OSError("synthetic unlink failure")
        path.unlink(missing_ok=True)

    fakes.artifact_remover = selective_remover

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "presentation_reconciliation_pending"
    assert "cleanup" in result.message.casefold()
    assert blocked.exists()
    assert "private material" not in result.message
    assert all(not path.exists() for path in artifacts if path != blocked)


def test_oauth_artifact_cleanup_verifies_absence_after_apparent_success(tmp_path):
    fakes = Fakes(tmp_path)
    artifact = fakes.store.path.parent / "attempt-1.result.raw.log"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("private material", encoding="utf-8")
    fakes.artifact_remover = lambda path: None

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "presentation_reconciliation_pending"
    assert "cleanup" in result.message.casefold()
    assert artifact.exists()
    assert "private material" not in result.message
