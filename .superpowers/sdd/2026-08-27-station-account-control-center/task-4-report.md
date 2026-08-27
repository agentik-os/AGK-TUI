# Task 4 Report — Private Persistent Discord Account Control Center

## Verdict

**DONE_WITH_CONCERNS**

Task 4 is implemented and verified in the canonical dirty checkout. The new UI module and tests are committed. The two narrowly scoped startup-integration hunks in `adapter.py` are intentionally left uncommitted because that file contained extensive unrelated owner work before Task 4 began.

## Delivered behavior

- Adopts exact Station guild/category/channel/post identifiers:
  - guild `1541131439599386644`
  - category `1542505218569150585`
  - channel `1542563923809796140`
  - pinned post `1542563946135814278`
  - owner `1441423462492016821`
- Reconciles the existing artifact idempotently and edits/replaces disabled placeholder components rather than creating another post.
- Reasserts private channel permissions for `@everyone`, the exact owner, and the bot.
- Persists only channel/message IDs at `$HERMES_HOME/account_control_state.json`, atomically, mode `0600`.
- Registers a `timeout=None` persistent `AccountControlView` and reuses/binds that same registered view to the adopted post.
- Implements stable component IDs for provider/account selection, Switch, Add, Reconnect, Refresh, Close, Claude submit-code, and reconnect confirmation.
- Rechecks exact user, guild, and channel authorization on every callback and modal submission.
- Implements the canonical two-level Switch flow for both `openai-codex` and `anthropic` through `adapter._prefer_account_credential(provider, credential_id)`, followed by canonical roster reload/post refresh. The response explicitly states that automatic quota rotation remains enabled; the flow does not disable or mutate rotation.
- Implements owner-nickname Add modal, two-step Reconnect confirmation, selected-attempt-only Close, and Refresh.
- Uses the approved OAuth runner; polls only its redacted result artifact; OpenAI output includes only provider, alias, expiry, verification URL, and device code.
- Implements Claude `Submit code` button and modal. The modal snapshots the active attempt ID, reauthorizes, rejects a changed attempt, and delegates to `OAuthRunner.submit_claude_code`, which reserves and writes to the exact active FIFO without retaining the code.
- Uses the approved transaction coordinator seam on Refresh when the selected attempt has reached `succeeded`.
- Adds no new slash command; `/account` remains untouched.

## Files

### Created and committed

- `hermes/plugins/platforms/discord/agk_account_control_ui.py`
- `tests/test_agk_account_control_ui.py`

### Modified, intentionally uncommitted

- `hermes/plugins/platforms/discord/adapter.py`
  - imports `ACCOUNT_CONTROL_GUILD_ID`, `register_account_control_center`, and `reconcile_account_control_channel`
  - calls registration and reconciliation inside Discord `on_ready`
  - catches/logs only exception type so provider data and secrets cannot enter logs

### Report and snapshots

- `.superpowers/sdd/2026-08-27-station-account-control-center/task-4-report.md`
- `.superpowers/sdd/2026-08-27-station-account-control-center/snapshots/task-4-20260827T211645Z/adapter.before.py`
- `.superpowers/sdd/2026-08-27-station-account-control-center/snapshots/task-4-20260827T211645Z/adapter.before.diff`
- `.superpowers/sdd/2026-08-27-station-account-control-center/snapshots/task-4-20260827T211645Z/adapter.after.py`
- `.superpowers/sdd/2026-08-27-station-account-control-center/snapshots/task-4-20260827T211645Z/adapter.task4.diff`

Snapshot SHA-256 values:

- before adapter: `af3eb2cedda41ea9b360af068ebbb370da522532944d77cab5278522675c961a`
- before pre-existing diff: `9d17b5d833d65a3e71b6358ee9a4d87ddde013c684205cef952b8584374f6c46`
- after adapter: `30111d43d49d2438c705b663f23238756353c41476ac2315677567e969ff97a3`
- Task 4 before/after adapter patch: `c0a9a0014a65ae05b71a6a0b7b8a2b96b370513e599e80e51917ba43fdbb1cb3`

## TDD evidence

### RED

1. Initial reconciliation test failed at collection with:
   - `AssertionError: agk_account_control_ui.py does not exist`
2. Authorization and Switch tests then failed because `AccountControlView` had no runner injection/dispatch implementation:
   - `TypeError: AccountControlView.__init__() got an unexpected keyword argument 'runner'`
3. Add/Reconnect/Close/Claude tests failed on absent methods/actions:
   - `AttributeError: 'AccountControlView' object has no attribute 'start_add'`
   - reconnect and close produced no runner calls
   - `AttributeError: ... no attribute 'submit_claude_code'`
4. Adapter integration test failed because `on_ready` did not contain registration/reconciliation.
5. Existing-artifact privacy and persistent-view binding tests failed because permissions were not reasserted and the registered view was not reused.
6. Delayed OAuth result test failed with one read (`result_calls == 1`).
7. Transaction coordinator test failed because Refresh did not finalize the succeeded attempt.

### GREEN

Final dedicated UI run:

```text
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pytest-asyncio --with pyyaml pytest -q tests/test_agk_account_control_ui.py
.......................................                                  [100%]
39 passed in 0.21s
```

## Verification commands and outputs

Prescribed three-file command was attempted exactly and exposed a pre-existing test-environment dependency omission:

```text
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pytest-asyncio --with pyyaml pytest -q tests/test_agk_account_control_ui.py tests/test_discord_station_session_ui.py tests/test_agk_account_usage_monitor.py
ERROR tests/test_agk_account_usage_monitor.py
ModuleNotFoundError: No module named 'httpx'
```

The same requested set with the missing runtime dependency explicitly supplied passed:

```text
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pytest-asyncio --with pyyaml --with httpx pytest -q tests/test_agk_account_control_ui.py tests/test_discord_station_session_ui.py tests/test_agk_account_usage_monitor.py
61 passed in 0.20s
```

Full Task 1–4 plus related Discord regression set:

```text
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pytest-asyncio --with pyyaml --with httpx pytest -q tests/test_agk_account_control.py tests/test_agk_account_oauth.py tests/test_agk_account_transactions.py tests/test_agk_account_control_ui.py tests/test_discord_station_session_ui.py tests/test_agk_account_usage_monitor.py
147 passed in 0.66s
```

Additional checks:

```text
python3 -m py_compile hermes/plugins/platforms/discord/agk_account_control_ui.py tests/test_agk_account_control_ui.py
# PASS

git diff --check -- hermes/plugins/platforms/discord/agk_account_control_ui.py tests/test_agk_account_control_ui.py hermes/plugins/platforms/discord/adapter.py
# PASS

# Real installed discord.py construction check
runtime-ui-ok 7 agkacct:claude-code-modal
```

## Commit

- `f26597c feat(discord): add private account control center`
  - contains only the new Task 4 UI module and tests
  - does not contain `adapter.py` or any unrelated dirty-checkout changes

## Uncommitted scoped adapter integration

The exact Task 4 adapter delta is preserved at `adapter.task4.diff`. It consists only of:

1. relative/fallback imports for the Task 4 UI module
2. guarded `on_ready` registration and reconciliation

Parent review/deployment should apply or selectively stage that scoped patch against the intentionally dirty canonical adapter. Do not stage the whole adapter without reconciling its unrelated pre-existing modifications.

## Self-review

- Authorization is fail-closed on exact snowflake IDs and runs before all action dispatch.
- Modal submissions call the same authorization gate again.
- No credential token or one-time code is stored in UI state, JSON state, Discord text, or logs.
- OAuth payload rendering is allowlist-based; token/password/secret query keys invalidate the URL.
- The persistent state contains only channel/message IDs.
- The exact live post is fetched before persisted fallback IDs; a new post is sent only when neither exists.
- Repeated reconciliation reuses the same channel, message, and registered view.
- Close passes only `selected_attempt_id` to the runner.
- Switch uses only the canonical adapter preference seam and does not modify rotation controls.

## Concerns

1. **Live Discord readback was not executed from this subagent session.** The exact IDs are covered by reconciliation tests and runtime construction, but deployment/restart and a real Discord fetch/edit readback remain a parent/operator step.
2. **`adapter.py` integration is intentionally uncommitted** to avoid capturing extensive unrelated pre-existing edits. The parent must review/apply `adapter.task4.diff` before deployment.
3. The prescribed test command omits `httpx`, which the already-approved Task 1 account module imports. Supplying `--with httpx` makes the full requested regression set pass.

---

# Fix Round 1 — 2026-08-27

## Verdict

**DONE_WITH_CONCERNS**

All static/code-level Critical, Important, and Minor findings from `task-4-review.md` are closed in commit `c93eb20`. The remaining concern is external runtime evidence: this session had no authenticated live Discord readback, so the exact deployed ACL/pin/view state still requires operator verification after restart.

## Fixes delivered

- Reconciliation now adopts only the exact guild/category/channel/post bindings, fails closed instead of using saved-ID/category/post fallbacks, serializes overlapping runs, treats only Discord `NotFound` as absence, refuses replacement posts, and atomically replaces plus reads back the complete three-target ACL (`@everyone`, exact owner, bot).
- OAuth URLs now use provider-specific HTTPS host/path allowlists, reject userinfo/fragments/unknown or sensitive query keys/ports/paths, reconstruct safe URLs, cap fields, and omit the extra OpenAI provider line.
- Production registration constructs the Task 2 `OAuthAttemptStore`/`OAuthRunner` and Task 3 `AccountTransactionCoordinator`, with durable mode-0600 pre-OAuth pool snapshots, candidate probing, canonical transaction defaults, and startup-to-Refresh coverage.
- Canonical Switch statuses (`saved`, `missing`, `unavailable`) are handled explicitly; success requires canonical roster ordering readback and automatic quota rotation remains untouched.
- Add, Reconnect, Claude Submit, and Claude modal flows bind immutable provider/account/attempt snapshots. Every callback/modal path reauthorizes exact owner/guild/channel before acting.
- Transaction outcomes are surfaced with safe status-specific text. Reconciliation-required and presentation-pending attempts remain selected for action; committed/rolled-back terminal outcomes clear selection.
- Initial roster/provider I/O runs in `asyncio.to_thread`; slow-loader tests prove the Discord loop yields.
- Roster output is bounded to Discord's 2,000-character limit. Action/provider/post-edit failures are redacted and returned ephemerally instead of escaping as generic interaction failures.

## TDD evidence

RED runs observed failures for each fix group, including unauthorized ACL survivors, userinfo/fragment/host/query URL leaks, absent production service construction, canonical Switch false-success, transient fetch swallowing, event-loop blocking, hidden transaction outcomes, stale controls, unbounded content, escaped exceptions, and mutable Add/attempt provider context.

Final GREEN verification:

```text
# Dedicated Task 4 suite
66 passed, 3 skipped in 0.28s

# Real discord.py modal authorization (wrong user, guild, channel)
3 passed, 66 deselected in 0.12s

# Task 1–4 + related Discord regression suite
174 passed, 3 skipped in 0.73s

# Prescribed UI/session/usage subset (with required httpx)
89 passed, 3 skipped in 0.34s

python3 -m py_compile ...
# PASS

git diff --check -- ...
# PASS
```

The three normal-suite skips are the same modal runtime cases exercised separately with real `discord.py`, where all three pass.

## Commits and adapter preservation

- Task 4 module/tests: `c93eb20 fix(discord): harden account control center`
- Fresh Fix Round 1 adapter before snapshot SHA-256: `30111d43d49d2438c705b663f23238756353c41476ac2315677567e969ff97a3`
- Fresh pre-existing adapter diff snapshot SHA-256: `a773ae89df68bda805f0a0cad3558ccded8470d2732dca4b153e3f775b68da42`
- Adapter after Fix Round 1 SHA-256: `30111d43d49d2438c705b663f23238756353c41476ac2315677567e969ff97a3` (identical; no adapter edits made in this round)
- Existing exact Task 4 integration patch SHA-256 remains `c0a9a0014a65ae05b71a6a0b7b8a2b96b370513e599e80e51917ba43fdbb1cb3`.

`adapter.py` remains intentionally uncommitted because it is heavily dirty with unrelated owner work. The existing tiny Task 4 import/`on_ready` integration hunk is unchanged and preserved at `snapshots/task-4-20260827T211645Z/adapter.task4.diff`; selectively committing the whole file remains unsafe.

## Remaining issue

- **Live Discord readback not executed:** after deployment/restart, verify exact guild/category/channel/post IDs, exactly three ACL overwrite targets with only owner/bot allowed, one pinned post, and one persistent registered view.
