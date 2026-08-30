# Task 3 report — Transactional Add/Reconnect coordinator

Status: **DONE**

## Files

- Created `hermes/plugins/platforms/discord/agk_account_transactions.py`
- Created `tests/test_agk_account_transactions.py`
- Created this report: `.superpowers/sdd/2026-08-27-station-account-control-center/task-3-report.md`

## Implementation

Implemented immutable `TransactionResult` and `AccountTransactionCoordinator.finalize(attempt_id)`.

The coordinator now:

1. requires the OAuth initiator's immutable pre-OAuth pool-ID snapshot;
2. creates a timestamped mode-`0700` backup directory before mutation;
3. writes mode-`0600` copies of `auth.json`, `config.yaml`, and `provider-account-aliases.json` plus a mode-`0600` SHA-256 JSON manifest;
4. discovers exactly one candidate by comparing pre/post canonical pool IDs and rejects duplicate IDs;
5. passes the exact candidate pool entry to an injected bounded inference probe;
6. fetches candidate usage and safely records `usage unavailable` without blocking a verified candidate;
7. atomically binds the owner nickname and re-reads the candidate before old removal;
8. removes the old credential only for reconnect and only after all prior gates;
9. re-reads the final canonical pool and asserts exact counts;
10. refreshes presentation surfaces only after commit;
11. removes FIFO/result/raw-log OAuth artifacts on terminal paths;
12. uses injected pool/probe/usage/remove/refresh seams so tests never mutate live credentials.

Exact result statuses implemented and exercised:

- `committed`
- `rolled_back`
- `reconciliation_required`
- `presentation_reconciliation_pending`

## TDD evidence

### Initial RED

Command:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml pytest -q tests/test_agk_account_transactions.py
```

Observed expected failure before production code existed:

```text
FF                                                                       [100%]
AssertionError: transaction coordinator does not exist
2 failed in 0.03s
```

### Additional rollback RED

After adding duplicate-candidate reconciliation coverage, the new test failed for the intended behavioral gap:

```text
......F...                                                               [100%]
FAILED tests/test_agk_account_transactions.py::test_duplicate_candidate_ids_are_not_committed
E AssertionError: assert 'rolled_back' == 'reconciliation_required'
1 failed, 9 passed in 0.05s
```

The implementation was changed to verify candidate absence after canonical cleanup and return reconciliation-required when a duplicate remains.

### Usage-unavailable RED

A new usage failure test initially proved that unavailability was not represented in the safe transaction result:

```text
F                                                                        [100%]
E AssertionError: assert 'usage unavailable' in 'credential change committed.'
1 failed in 0.04s
```

The implementation was changed to retain only a safe availability boolean and return a whitelisted `usage unavailable` message without retaining provider response material.

### GREEN

Focused Task 3 command:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml pytest -q tests/test_agk_account_transactions.py
```

Output:

```text
...........                                                              [100%]
11 passed in 0.03s
```

Affected Task 1–3 regression command:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml --with httpx pytest -q \
  tests/test_agk_account_control.py tests/test_agk_account_oauth.py \
  tests/test_agk_account_transactions.py
```

Output:

```text
.................................................................        [100%]
65 passed in 0.20s
```

Static checks:

```bash
python -m py_compile hermes/plugins/platforms/discord/agk_account_transactions.py \
  tests/test_agk_account_transactions.py
git diff --check -- hermes/plugins/platforms/discord/agk_account_transactions.py \
  tests/test_agk_account_transactions.py
```

Output: clean, exit `0`.

## Tested behavior

- reconnect ordering proves backup → discovery → exact probe → usage → nickname bind → candidate reread → old removal → final reread → refresh;
- failed exact-candidate probe preserves the old credential;
- backups have exact directory/file modes and verified SHA-256 checksums;
- registry write failure restores aliases and removes only the candidate;
- candidate cleanup failure returns `reconciliation_required`;
- canonical old-removal failure retains both fixture credentials and never reports success;
- duplicate candidate IDs cannot commit;
- post-commit refresh failure preserves committed canonical state and returns `presentation_reconciliation_pending`;
- add commits exactly one candidate without removing existing credentials;
- usage failure records only safe unavailability;
- OAuth FIFO/result/raw-log artifacts are removed on rollback.

## Rollback and security self-review

- Old removal is unreachable until exact-candidate inference, usage observation, atomic nickname bind, and candidate reread have completed.
- Pre-commit failures restore the prior alias snapshot and canonically remove only the discovered candidate.
- Candidate cleanup is verified by re-reading the pool; ambiguity is never labeled rolled back.
- Old-removal failure is re-read before reporting whether both credentials were retained.
- Final count mismatch is never reported as committed.
- Refresh failure occurs after credential commit and therefore does not destructively roll back canonical credentials.
- Backup reads use `O_NOFOLLOW` where available and reject non-regular files.
- Stable IDs are allowlisted and secret-shaped/overlong IDs are rejected before inclusion in results or paths.
- No subprocess/argv secret transport, printing, provider error-body logging, or credential persistence was added.
- Usage response objects are discarded; only availability affects the safe result message.
- Tests use synthetic credential fixtures and injected seams; no live account mutation was performed.

## Commit

- `57ddd1a feat(auth): add transactional account replacement`
- Commit contains only the two approved Task 3 implementation/test files.

## Concerns

- None for Task 3. Task 4 must capture and pass the immutable pre-OAuth pool-ID snapshot and provide the exact-credential probe and refresh seams; the coordinator intentionally does not infer a baseline from aliases or run an unscoped probe.

---

# Fix Round 1 — transactional safety and replay hardening

Status: **DONE**

## Findings closed

- Added an explicit durable `irreversible` phase before canonical old-credential removal. Once removal is attempted, exceptions, malformed entries, read failures, and mutate-then-raise behavior cannot enter candidate rollback.
- Added a mode-`0700` transaction directory, mode-`0600` global `flock`, and atomically replaced/fsynced per-attempt state. Terminal outcomes are memoized; sequential and concurrent replay returns the stored outcome without rerunning credential mutation.
- Replaced count-only reconciliation with exact `Counter` multiset equality both before old removal and at final reconciliation. Rogue replacement, unrelated removal, and duplicate substitution are rejected; reordering remains valid.
- OAuth FIFO/result/raw-log cleanup now uses an injected removal seam, verifies artifact absence, and surfaces deletion or verification failure as reconciliation/security pending without including paths or content.
- Added direct production `AliasRegistry` coverage proving mode-`0600` temporary content, `os.replace` atomicity, old-file visibility until replacement, exact readback, and temporary cleanup.
- Added safe handling for malformed durable state and replay-time outcome-persistence failure; both return non-destructive reconciliation results.

## RED evidence

- Irreversible boundary: `2 failed, 1 passed, 11 deselected`; final read failure and malformed final entry removed the candidate before the fix.
- Exact multiset: `2 failed, 2 passed, 14 deselected`; same-count rogue and duplicate substitutions incorrectly committed.
- Replay/concurrency: `2 failed, 18 deselected`; sequential and concurrent repeats returned `rolled_back` and removed the committed candidate.
- OAuth cleanup: `3 failed, 1 passed, 19 deselected`; FIFO/result/raw-log deletion failures incorrectly returned `committed`.
- Replay persistence/state corruption: `2 failed, 27 deselected`; both paths raised instead of returning reconciliation.

All RED probes used injected synthetic seams and temporary directories; no live credential mutation was performed.

## GREEN and quality evidence

Focused Task 3:

```text
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml pytest -q tests/test_agk_account_transactions.py
29 passed in 0.35s
```

Task 1–3 regression:

```text
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml --with httpx pytest -q tests/test_agk_account_control.py tests/test_agk_account_oauth.py tests/test_agk_account_transactions.py
83 passed in 0.46s
```

Static and repository checks:

```text
python -m py_compile hermes/plugins/platforms/discord/agk_account_transactions.py tests/test_agk_account_transactions.py
uv run --with ruff ruff check hermes/plugins/platforms/discord/agk_account_transactions.py tests/test_agk_account_transactions.py
All checks passed!
git diff --check -- <Task 3 implementation, tests, and report>
clean (exit 0)
secret scan: private_key=0 bearer=0 api_key=0 openai_key=0
```

## Fix commit

- `3f6e26e fix(auth): harden account transaction finalization`
- Commit contains only `agk_account_transactions.py` and `test_agk_account_transactions.py`.

## Fix Round 1 concerns

- None. Durable locking uses Linux/POSIX `flock`, matching the Station deployment platform.
