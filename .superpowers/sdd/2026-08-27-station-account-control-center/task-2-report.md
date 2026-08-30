# Task 2 Report — Durable OAuth Attempt Store and Runner

## Status

DONE_WITH_CONCERNS

## Outcome

Implemented the durable OAuth attempt store and sibling user-systemd OAuth runner for only `openai-codex` and `anthropic`. No Discord files or live account-control channel/post were modified.

## Files created

- `hermes/plugins/platforms/discord/agk_account_oauth.py`
  - `OAuthAttempt`
  - atomic, lock-protected `OAuthAttemptStore`
  - `OAuthRunner.start()`
  - `OAuthRunner.submit_claude_code()`
  - `OAuthRunner.cancel()`
- `scripts/agk_provider_oauth_runner.py`
  - provider/alias/timeout allowlisting
  - exact Hermes OAuth argv construction
  - transient PTY execution through `script -qec`
  - mode-0600 FIFO, raw log, and redacted result state
  - authorization URL/device-code/status-only parsing
  - cleanup of FIFO and raw log on normal, failure, and exception paths
- `tests/test_agk_account_oauth.py`
  - 12 lifecycle, persistence, ownership, allowlist, redaction, and cleanup tests

## TDD evidence

### Initial RED

Command:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml pytest -q tests/test_agk_account_oauth.py
```

Observed output before production files existed:

```text
EEEEEEEEEE                                                               [100%]
AssertionError: agk_account_oauth.py does not exist
AssertionError: agk_provider_oauth_runner.py does not exist
10 errors in 0.09s
```

The failure was expected and caused by the missing Task 2 modules.

### Initial GREEN

Command:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml pytest -q tests/test_agk_account_oauth.py
```

Observed:

```text
..........                                                               [100%]
10 passed in 0.03s
```

### Real Codex-output regression RED → GREEN

Inspection of `/home/operator/src/hermes-agent/hermes_cli/auth.py` showed that Codex emits an ANSI-colored URL and device code on lines following their prompts. A regression test reproducing that exact output initially failed:

```text
FAILED tests/test_agk_account_oauth.py::test_runner_parses_real_codex_multiline_ansi_prompt
1 failed in 0.04s
```

After ANSI stripping and multiline prompt parsing:

```text
1 passed in 0.01s
11 passed in 0.04s
```

### Token-bearing URL regression RED → GREEN

A regression test proved that a token-bearing query could otherwise be retained as an authorization URL:

```text
FAILED tests/test_agk_account_oauth.py::test_runner_rejects_token_bearing_authorization_url
1 failed in 0.04s
```

After rejecting URLs with sensitive query keys, userinfo, or fragments:

```text
1 passed in 0.01s
12 passed in 0.03s
```

## Final verification

Focused Task 2 command:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml pytest -q tests/test_agk_account_oauth.py
```

Output:

```text
............                                                             [100%]
12 passed in 0.03s
```

Affected account-control regression set:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml --with httpx pytest -q \
  tests/test_agk_account_oauth.py tests/test_agk_account_control.py \
  tests/test_agk_account_usage_monitor.py
```

Output:

```text
.............................................                            [100%]
45 passed in 0.14s
```

Static checks:

```bash
python3 -m py_compile tests/test_agk_account_oauth.py \
  hermes/plugins/platforms/discord/agk_account_oauth.py \
  scripts/agk_provider_oauth_runner.py
git diff --check 91f0f16^ 91f0f16
```

Output: clean; both commands exited 0.

The first broader regression invocation omitted `httpx` and stopped during collection of the pre-existing account usage monitor dependency. Re-running with `--with httpx` produced the clean 45-test result above.

## Security review

- Provider allowlist is exactly `openai-codex` and `anthropic`.
- Hermes child argv is exactly:
  - `hermes auth add <allowlisted-provider> --type oauth --label <validated-technical-alias> --no-browser --timeout 900`
- Transient unit argv contains only the provider, technical alias, FIFO path, redacted state path, and fixed timeout, plus executable/control arguments.
- OAuth authorization codes, access/refresh tokens, passwords, and API keys are never placed in argv or the durable attempt store.
- Claude authorization code is delivered only through a mode-0600 FIFO and is never copied into retained JSON.
- Attempt metadata is atomically persisted under `state/account-oauth/attempts.json`; attempt file and lock are mode 0600, parent directory mode 0700.
- Concurrent attempt mutations use `flock`; a new live provider/nickname attempt cancels the prior live record atomically.
- Runner state JSON uses an explicit field allowlist: status, validated authorization URL, and device code only.
- Authorization URLs with sensitive query keys, URL credentials, or fragments are rejected.
- Raw PTY output is held only in a mode-0600 temporary raw log and deleted with the FIFO in the runner's terminal cleanup path.
- No `shell=True`; the only shell command string is produced by `shlex.join()` from the fully allowlisted exact Hermes argv for `script -qec`.
- Cancellation validates the recorded systemd unit name before invoking `systemctl --user stop`.
- No Discord implementation or persistent channel/post was changed.

## Commit

- `91f0f16 feat(auth): add durable Discord OAuth attempts`
  - Exactly the three Task 2 implementation/test files were committed.

## Concerns

- A live provider OAuth login and real transient user-systemd unit were intentionally not started because that would initiate an account-authentication side effect. The systemd argv, PTY command, FIFO delivery, redacted-state parsing, and cleanup boundaries are covered by deterministic tests.
- Independent subagent review was not requested because the task explicitly prohibited spawning subagents; the parent review remains the independent acceptance boundary.
- This report was written after the implementation commit so it can contain the final commit hash; it is intentionally not included in `91f0f16`.

---

## Fix Round 1 — 2026-08-27

### Status

DONE

### Findings resolved

- Authorization URL retention now fails closed through an explicit non-secret query-key allowlist plus normalized credential-key rejection. URLs carrying authorization codes, token classes, client secrets, API-key variants, password variants, userinfo, or fragments are not persisted.
- The original `expires_at` is enforced by both a transient-unit `RuntimeMaxSec` bound and an absolute runner deadline. The required Hermes child command still uses `--timeout 900` exactly.
- Guarded compare-and-set transitions reserve start, submission, and cancellation. Cancellation cannot be overwritten by a late start or FIFO completion, duplicate starts/submissions are rejected, and backward or terminal status transitions are blocked.
- `OAuthRunner.create()` performs runner-aware replacement. A live conflicting unit must stop and verify inactive before its ephemeral artifacts are removed and a replacement is created; direct metadata-only replacement fails closed for running conflicts.
- Cancellation checks the stop result and verifies the unit is inactive before reporting success or deleting artifacts. A stop failure preserves live state and artifacts; cancellation intent remains durable during the unit-visibility start race.
- `OAuthAttemptStore.get()` reconciles allowlisted terminal runner result status into `attempts.json` and durably expires stale live attempts.
- Claude submission is atomically reserved, bounded to the full `PIPE_BUF` frame, and accepted only when the writer reports the complete byte count. Partial writes never become submitted.

### TDD evidence

Initial adversarial regression run before production changes:

```text
16 failed, 12 passed in 0.21s
```

The failures reproduced every independent-review class: unsafe URL retention, late-start lifetime extension, start/cancel and duplicate-start races, metadata-only replacement, fail-open cancellation, missing durable reconciliation/expiry, and partial/submission races.

A further unit-visibility race regression was captured RED before its fix:

```text
1 failed in 0.07s
```

The monotonic live-transition regression was also captured RED before tightening the state graph:

```text
1 failed in 0.06s
```

Final focused suite:

```text
33 passed in 0.07s
```

### Final verification

Affected account-control suites:

```text
66 passed in 0.19s
```

Quality and security gates:

- Ruff on the three Task 2 source/test files: `All checks passed!`
- `py_compile` on the three Task 2 source/test files: exit 0
- `git diff --check` on the Task 2 implementation diff: exit 0
- Production-file secret-pattern scan: `0` hits

### Commit

- `5573d46 fix(auth): harden durable OAuth attempts`
  - Exactly the three Task 2 implementation/test files were committed.

### Concerns

- No live OAuth login was started; authentication side effects remain deferred to the Task 6 acceptance boundary. Systemd lifecycle, absolute deadline, redaction, reconciliation, FIFO, and cleanup behavior are covered deterministically.
- No independent subagent was spawned because this Fix Round explicitly prohibited subagents; the parent review remains the independent acceptance boundary.

---

## Fix Round 2 — 2026-08-27

### Status

DONE

### Findings resolved

- Authorization URL filtering now rejects `device_code` and normalized code-bearing key variants such as `device-code` and `deviceCode`. The UI-safe user/device code remains available only through the separately parsed `device_code` result field.
- Cancellation now accepts only the explicit `systemctl is-active` inactive/not-found outcomes (exit 3 or 4). Active state and indeterminate command, manager, or transport failures fail closed, restore the prior non-starting live state, preserve artifacts, and skip `reset-failed`.
- A failed `systemd-run` now reconciles both possible reservations deterministically: `starting` becomes `failed`, while a winning `cancelling` intent becomes `cancelled`. The never-created runner unit is cleared and ephemeral FIFO/result/raw-log files are removed.

### TDD evidence

The three adversarial regressions were run before production changes. The expected RED result was:

```text
3 failed, 9 passed in 0.09s
```

Failures independently reproduced retention of `device_code=SECRET-DEVICE`, fail-open cancellation on `is-active` exit 1, and a failed-start race stranded in `cancelling`.

After the minimal implementation, the targeted regression command produced:

```text
12 passed in 0.03s
```

### Final verification

Focused Task 2 suite:

```text
39 passed in 0.12s
```

Affected account-control suites:

```text
72 passed in 0.19s
```

Quality and security gates:

- Ruff on the three Task 2 source/test files: `All checks passed!`
- `py_compile` on the three Task 2 source/test files: exit 0
- `git diff --check` on the scoped Task 2 diff: exit 0
- Production-file secret-pattern scan: `0` hits

### Commit

- `318171b fix(auth): close OAuth cancellation gaps`
  - Exactly the three Task 2 implementation/test files were committed.

### Concerns

- No live OAuth login or transient user-systemd unit was started because either would initiate an authentication side effect. The URL redaction and cancellation interleavings are covered by deterministic adversarial tests.
- No independent subagent was spawned because this Fix Round explicitly prohibited subagents; the parent review remains the independent acceptance boundary.
