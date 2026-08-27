# Task 5 Report — Bootstrap, Legacy Removal, Installation, Refresh

## Verdict

**DONE_WITH_CONCERNS**

Task 5 behavior is implemented and verified. Canonical Task 5 changes are committed as `5191d28`. The Station overlay is byte-synchronized to the intentionally dirty canonical working tree, but is intentionally left uncommitted because committing it would absorb unrelated/pre-existing Station and AGK-TUI edits.

## Implemented

- Added Operator-main-profile bootstrap configuration via `hermes config set` for:
  - `account_control_enabled=true`
  - category `1542505218569150585`
  - owner `1441423462492016821`
  - channel name `account-control`
  - OAuth timeout `900`
- Preserved voice monitor bootstrap for category `1542505218569150585`, seed voice channel `1542505478679171164`, and 300-second interval.
- Removed legacy Claude/summary text-channel lookup, creation, config names, and text-panel upserts from the usage monitor.
- Preserved the busiest-window voice rule (`min(remaining)` -> greatest used percentage).
- Installed `scripts/agk_provider_oauth_runner.py` explicitly into the install tree; Discord account modules remain installed atomically through the canonical `platforms/discord` directory copy.
- Added `DiscordAdapter.refresh_account_surfaces(reason=...)`, which re-renders the persistent account-control view and invokes exactly one monitor `refresh_once()` without restarting the gateway or an account.
- Invoked `await adapter.refresh_account_surfaces(reason="account-transaction")` only after a committed account transaction and avoided a duplicate outer message render.
- Mirrored canonical bootstrap, adapter, all five account modules, and OAuth runner into `/home/operator/src/Station/overlay/`.

## Canonical files changed

- `scripts/sync-hermes.sh`
- `install.sh`
- `hermes/plugins/platforms/discord/adapter.py`
- `hermes/plugins/platforms/discord/agk_account_control_ui.py`
- `hermes/plugins/platforms/discord/agk_account_usage_monitor.py`
- `tests/test_agk_account_control_install.py` (new)
- `tests/test_agk_account_control_ui.py`

## Station overlay files synchronized

- `overlay/install.sh`
- `overlay/scripts/sync-hermes.sh`
- `overlay/scripts/agk_provider_oauth_runner.py`
- `overlay/hermes/plugins/platforms/discord/adapter.py`
- `overlay/hermes/plugins/platforms/discord/agk_account_control.py`
- `overlay/hermes/plugins/platforms/discord/agk_account_control_ui.py`
- `overlay/hermes/plugins/platforms/discord/agk_account_oauth.py`
- `overlay/hermes/plugins/platforms/discord/agk_account_transactions.py`
- `overlay/hermes/plugins/platforms/discord/agk_account_usage_monitor.py`

All synchronized source/destination pairs were read back and SHA-256 verified as `MATCH` immediately after copying.

## Dirty-file preservation

Snapshots were taken before modifying every dirty target under:

- `.superpowers/sdd/2026-08-27-station-account-control-center/task-5-snapshots/pre-20260827T221134Z/`

Snapshot coverage:

- AGK-TUI: `adapter.py`, `install.sh`, `scripts/sync-hermes.sh`
- Station overlay: `adapter.py`, `agk_account_usage_monitor.py`, `install.sh`, `scripts/sync-hermes.sh`

Task 5 hunks for dirty AGK-TUI files were staged from clean `HEAD` content through explicit, unique replacements, then reviewed with `git diff --cached`; unrelated working-tree edits remain unstaged and unchanged.

The exact uncommitted Station overlay patch is preserved at:

- `.superpowers/sdd/2026-08-27-station-account-control-center/task-5-station-overlay.patch`
- SHA-256: `a8e5cb8f2009908ed62212a17f472a479701ab12551f9df9ace42cb1d584bca6`
- Size: 153,152 bytes

Snapshots and the Station patch are intentionally uncommitted so the Task 5 commit does not absorb unrelated dirty work.

## TDD evidence

### RED

Command:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pytest-asyncio --with pyyaml pytest -q \
  tests/test_agk_account_control_install.py \
  tests/test_agk_account_control_ui.py::test_refresh_surfaces_safe_transaction_outcome
```

Result: **5 failed, 3 passed** for the expected missing behaviors:

- no account-control bootstrap config
- legacy text auto-create still present
- OAuth runner not explicitly installed
- overlay not synchronized
- committed transaction did not invoke immediate refresh

### GREEN — focused

Same focused command after implementation:

- **8 passed in 0.04s**

### GREEN — Tasks 1–5 affected suites

The brief's command first stopped during collection because the isolated `uv run` environment did not include the transitive `httpx` dependency. Re-run with `--with httpx`:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run \
  --with pytest --with pytest-asyncio --with pyyaml --with httpx pytest -q \
  tests/test_agk_account_control_install.py \
  tests/test_agk_account_control.py \
  tests/test_agk_account_oauth.py \
  tests/test_agk_account_transactions.py \
  tests/test_agk_account_control_ui.py \
  tests/test_agk_account_usage_monitor.py
```

Result in the dirty working tree:

- **172 passed, 3 skipped in 0.73s**

Result from a clean index export (`git checkout-index`) containing only the scoped Task 5 commit candidate:

- **172 passed, 3 skipped in 0.86s**

Additional checks:

```bash
bash -n install.sh scripts/sync-hermes.sh \
  /home/operator/src/Station/overlay/install.sh \
  /home/operator/src/Station/overlay/scripts/sync-hermes.sh
python3 -m py_compile \
  hermes/plugins/platforms/discord/agk_account_usage_monitor.py \
  hermes/plugins/platforms/discord/agk_account_control_ui.py \
  scripts/agk_provider_oauth_runner.py
git diff --cached --check
```

All passed. Direct source scan confirmed no legacy IDs/names and no `create_text_channel` path in the monitor/bootstrap targets.

## Commits

- `5191d28 feat(station): provision account control center`

The commit contains only scoped Task 5 canonical code/tests. Pre-existing edits in `adapter.py`, `install.sh`, and `scripts/sync-hermes.sh` remain unstaged.

## Self-review

- No direct `config.yaml` or `.env` account-control settings were added.
- No live Discord, provider, OAuth, account, or Hermes config mutation was executed.
- No subagents were spawned.
- Legacy deleted IDs are absent from bootstrap sources.
- Legacy text channel names and all text-channel creation paths are absent from the usage monitor.
- Immediate refresh does not call start/stop/restart and invokes monitor refresh once.
- Persistent post refresh is not duplicated by the outer view refresh path.
- Voice naming still selects the most-consumed quota window.

## Concerns

1. `/home/operator/src/Station` is a separate, already dirty repository. Its exact synchronized overlay remains uncommitted to avoid absorbing unrelated/pre-existing edits. The complete patch and before snapshots are preserved above.
2. The canonical AGK-TUI working tree remains intentionally dirty after the scoped commit; remaining diffs in the three dirty Task 5 files are pre-existing/unrelated to the committed Task 5 hunks.
3. No runtime/live Discord verification was performed because the task explicitly prohibited live Discord/API/provider mutations; verification is automated and source/install-contract based.
