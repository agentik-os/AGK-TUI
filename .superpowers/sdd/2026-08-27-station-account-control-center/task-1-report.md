# Task 1 Report — Canonical Account Roster and Alias Registry

## Status

DONE

## Outcome

Implemented the Task 1 account-control domain and owner-keyed voice binding migration exactly in the canonical dirty checkout. Existing uncommitted account usage monitor work was preserved and committed with the Task 1 changes; no unrelated paths were staged or committed.

## Files

- Created `hermes/plugins/platforms/discord/agk_account_control.py`
  - `UsageWindow`
  - frozen `AccountRecord`
  - `AliasRegistry` with snapshot, replace, bind, remove, and bidirectional lookup
  - atomic temporary-file replacement, fsync, and mode `0600`
  - canonical v1 roster loading for `openai-codex` and `anthropic`
  - redacted whitelist-only roster rendering
  - owner-keyed `voice_binding_key`
- Modified/preserved `hermes/plugins/platforms/discord/agk_account_usage_monitor.py`
  - state-store support for `voice-owner:` keys
  - owner-key lookup before legacy credential-key lookup
  - migration from `voice:{provider}:{credential_id}` to `voice-owner:{provider}:{owner.casefold()}`
  - stale legacy key removal from the atomically saved state
- Created `tests/test_agk_account_control.py`
  - stable-ID alias join and private-field redaction
  - atomic alias rebinding and mode checks
  - credential removal isolation
  - binding-key case folding
- Modified/preserved `tests/test_agk_account_usage_monitor.py`
  - owner-key state persistence
  - owner-key channel bindings
  - legacy credential-binding migration

## TDD Evidence

### RED — roster and alias domain

Command:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with httpx --with pyyaml pytest -q \
  tests/test_agk_account_control.py::test_roster_joins_nickname_by_stable_id_and_redacts_private_fields \
  tests/test_agk_account_control.py::test_alias_registry_rebinds_nickname_atomically
```

Observed output before implementation:

```text
FF                                                                       [100%]
FAILED ...test_roster_joins_nickname_by_stable_id_and_redacts_private_fields
FAILED ...test_alias_registry_rebinds_nickname_atomically
AssertionError: canonical account-control module does not exist
2 failed in 0.03s
```

The first attempt reported fixture setup errors for the same missing-module reason. The test loader was corrected so the required RED evidence was an expected assertion failure rather than a test collection/setup error, then rerun to produce the failure above.

### RED — owner-key state and legacy migration

Command:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with httpx --with pyyaml pytest -q \
  tests/test_agk_account_usage_monitor.py::test_state_file_contract_is_profile_local_and_contains_only_message_ids \
  tests/test_agk_account_usage_monitor.py::test_voice_channel_sync_migrates_legacy_credential_binding_to_owner_key
```

Observed output before implementation:

```text
FF                                                                       [100%]
FAILED ...test_state_file_contract_is_profile_local_and_contains_only_message_ids
FAILED ...test_voice_channel_sync_migrates_legacy_credential_binding_to_owner_key
2 failed in 0.05s
```

Failures showed that `voice-owner:` keys were filtered from persisted state and that the legacy credential key remained unchanged.

### GREEN — focused Task 1 suite

Command:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with httpx --with pyyaml pytest -q \
  tests/test_agk_account_control.py tests/test_agk_account_usage_monitor.py
```

Observed before commit:

```text
..................                                                       [100%]
18 passed in 0.10s
```

Observed again after commit:

```text
..................                                                       [100%]
18 passed in 0.09s
```

## Additional Verification

Command:

```bash
git diff --check -- \
  hermes/plugins/platforms/discord/agk_account_usage_monitor.py \
  tests/test_agk_account_usage_monitor.py tests/test_agk_account_control.py
python3 -m py_compile \
  hermes/plugins/platforms/discord/agk_account_control.py \
  hermes/plugins/platforms/discord/agk_account_usage_monitor.py \
  tests/test_agk_account_control.py tests/test_agk_account_usage_monitor.py
```

Observed: exit code `0`, no output.

Staged-scope verification before commit:

```text
A hermes/plugins/platforms/discord/agk_account_control.py
A hermes/plugins/platforms/discord/agk_account_usage_monitor.py
A tests/test_agk_account_control.py
A tests/test_agk_account_usage_monitor.py
```

Post-commit path-scoped status for all four Task 1 paths was clean.

## Self-review

- Public interfaces match the brief, including the required `replace` helper exercised by the prescribed test.
- Alias persistence uses a same-directory temporary file, flush + fsync, chmod `0600`, and `os.replace`.
- Owner rebinding removes the prior stable-ID association case-insensitively before writing the replacement.
- Roster rendering constructs output solely from provider, nickname, stable credential ID, normalized status, priority, usage labels/remaining values, and reset timestamps. Entry labels, emails, tokens, and raw errors are never rendered.
- Missing usage remains `unavailable` rather than `0%`.
- `load_account_roster` scopes Hermes credential loading to the supplied home with the context-local Hermes home override instead of mutating process-global environment state.
- Voice synchronization resolves the owner key first, falls back to the legacy stable-ID key, writes the owner key, and removes the stale key before the state store's atomic save.
- No unrelated dirty-tree paths were staged, reformatted, reverted, reset, or committed.

## Commit

- `1e5586c` — `feat(discord): add canonical account roster`

## Concerns

None.

---

## Fix Round 1

### Status

DONE

### Findings addressed

- **I1 — unassigned voice collisions:** unassigned accounts now retain unique credential-scoped `voice:<provider>:<credential_id>` bindings. Owner-key migration occurs only after a valid nickname exists, and duplicate channel IDs are rejected within each synchronization pass. Two unassigned accounts remain distinct and stable over two passes.
- **I2 — forbidden content rendering:** the canonical alias boundary now accepts only known providers, safe stable IDs, and safe owner nicknames; it rejects email-, mention-, markdown-, control-, JWT-, API-key-, and opaque-secret-shaped nicknames. The renderer independently normalizes every public field, including provider, owner, credential ID, status, priority, usage label, percentage, and reset timestamp. The monitor now consumes `AliasRegistry.snapshot()` instead of bypassing canonical validation.
- **I3 — incomplete roster output:** provider IDs render as `OpenAI` and `Claude`; `reconnect required` is preserved; each available window renders both used and remaining percentages plus a validated reset timestamp.
- **I4 — existing registry permissions:** `snapshot()` opens with `O_NOFOLLOW` where available, requires a regular file, and repairs the open file descriptor to mode `0600` before reading.
- **M1 — malformed state root:** valid JSON with a non-dictionary root now fails open to `{}`.
- **M2 — scoped cleanup:** removed the dead `math` import, normalized imports/type annotations, retained intentional provider/Discord boundary fail-safe catches, and added safe exception-class-only diagnostics. Scoped Ruff is clean.

### Regression tests added

- `test_voice_channel_sync_keeps_unassigned_accounts_distinct_across_refreshes`
- `test_alias_registry_rejects_unsafe_owner_nicknames`
- `test_roster_renderer_normalizes_untrusted_public_fields`
- `test_roster_renderer_preserves_every_safe_account_state` (four states)
- `test_roster_renderer_uses_provider_labels_and_complete_usage_output`
- `test_alias_registry_repairs_existing_permissive_mode_before_read`
- `test_state_store_ignores_valid_json_with_non_mapping_root`
- `test_monitor_alias_loading_uses_canonical_validation_and_mode_repair`

### TDD evidence — RED

Each regression was run before its corresponding production change.

```text
I1: 1 failed in 0.12s
  Expected two unassigned channels and credential-scoped bindings; observed one channel renamed for the second account.

I2 registry boundary: 1 failed in 0.11s
  Failed: DID NOT RAISE ValueError for unsafe owner nicknames.

I2 renderer boundary: 1 failed in 0.10s
  Unsafe owner/provider/credential/usage/reset values were rendered verbatim.
  A follow-up priority-boundary regression also failed in 0.11s because an API-key-shaped priority was rendered.

I3: 2 failed, 3 passed in 0.12s
  `reconnect required` rendered as `unknown`; used percentages were absent.

I4: 1 failed in 0.11s
  Existing mode remained 0644 instead of 0600.

M1: 1 failed in 0.12s
  AttributeError: 'list' object has no attribute 'items'

Canonical monitor alias boundary: 1 failed in 0.12s
  Unsafe email-shaped alias remained present and mode repair was bypassed.
```

Representative RED commands:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with httpx --with pyyaml pytest -q \
  tests/test_agk_account_usage_monitor.py::test_voice_channel_sync_keeps_unassigned_accounts_distinct_across_refreshes

PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with httpx --with pyyaml pytest -q \
  tests/test_agk_account_control.py::test_alias_registry_rejects_unsafe_owner_nicknames \
  tests/test_agk_account_control.py::test_roster_renderer_normalizes_untrusted_public_fields \
  tests/test_agk_account_control.py::test_roster_renderer_preserves_every_safe_account_state \
  tests/test_agk_account_control.py::test_roster_renderer_uses_provider_labels_and_complete_usage_output \
  tests/test_agk_account_control.py::test_alias_registry_repairs_existing_permissive_mode_before_read

PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with httpx --with pyyaml pytest -q \
  tests/test_agk_account_usage_monitor.py::test_state_store_ignores_valid_json_with_non_mapping_root \
  tests/test_agk_account_usage_monitor.py::test_monitor_alias_loading_uses_canonical_validation_and_mode_repair
```

### GREEN and quality gates

Focused suite:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with httpx --with pyyaml pytest -q \
  tests/test_agk_account_control.py tests/test_agk_account_usage_monitor.py
```

```text
.............................                                            [100%]
29 passed in 0.11s
```

Scoped lint:

```bash
uv run --with ruff ruff check \
  hermes/plugins/platforms/discord/agk_account_control.py \
  hermes/plugins/platforms/discord/agk_account_usage_monitor.py \
  tests/test_agk_account_control.py tests/test_agk_account_usage_monitor.py
```

```text
All checks passed!
```

Compilation and whitespace verification:

```bash
python3 -m py_compile \
  hermes/plugins/platforms/discord/agk_account_control.py \
  hermes/plugins/platforms/discord/agk_account_usage_monitor.py \
  tests/test_agk_account_control.py tests/test_agk_account_usage_monitor.py
git diff --check -- <the four Task 1 Python paths>
```

Observed: exit code `0`, no output. Added-line security scan: `clean`.

### Self-review

- All four Important findings and M1 are covered by regressions that demonstrated the reported pre-fix failure.
- Unassigned voice identity remains stable without weakening assigned-owner migration.
- Alias reads enforce permissions on the opened descriptor and reject symlink/non-regular-file reads without exposing contents.
- Rendering is fail-closed for arbitrary public dataclass values; invalid values become fixed safe fallbacks rather than escaped secret material.
- Existing intentional external-boundary catches remain fail-safe; diagnostics include only provider/context and exception class, never raw response bodies, tokens, emails, or exception messages.
- Ruff, focused tests, byte compilation, diff checks, and staged-path/security checks passed.
- No unrelated dirty-tree files were staged, changed, reset, reformatted, or committed.
- No additional reviewer subagent was spawned, per the explicit task constraint; this round directly resolves the supplied independent review.

### Commit

- `6602274` — `fix(discord): address account roster review`

### Concerns

None.

---

## Fix Round 2

### Status

DONE

### Finding addressed

- **I2 — remaining secret/Discord-markdown bypass:** usage labels now fail closed to `Limit` when they begin with a recognized secret prefix, match a JWT shape, or contain underscore-based Discord markdown. Owner nickname validation now rejects underscores at both alias-registry ingestion and roster rendering boundaries. The provider monitor reuses the canonical usage-label normalizer, so its Discord panel cannot bypass the roster protection.
- Existing safe labels remain unchanged; exact-output coverage for `Session` and `Current week` continues to pass.

### Regression tests added

- `test_roster_renderer_rejects_secret_and_underscore_markdown_usage_labels`
- `test_owner_nickname_rejects_underscore_markdown_at_registry_and_render_boundaries`
- `test_provider_panel_rejects_secret_and_underscore_markdown_usage_labels`

### TDD evidence — RED

Command:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with httpx --with pyyaml pytest -q \
  tests/test_agk_account_control.py::test_roster_renderer_rejects_secret_and_underscore_markdown_usage_labels \
  tests/test_agk_account_control.py::test_owner_nickname_rejects_underscore_markdown_at_registry_and_render_boundaries \
  tests/test_agk_account_usage_monitor.py::test_provider_panel_rejects_secret_and_underscore_markdown_usage_labels
```

Observed before production changes:

```text
FFFF                                                                     [100%]
4 failed in 0.14s
```

The two roster label cases showed allowed-character secret-prefixed and double-underscore labels rendered verbatim. The owner regression showed `DID NOT RAISE ValueError`, and the provider panel also retained both unsafe labels.

### GREEN and quality gates

Focused suite:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with httpx --with pyyaml pytest -q \
  tests/test_agk_account_control.py tests/test_agk_account_usage_monitor.py
```

```text
.................................                                        [100%]
33 passed in 0.12s
```

Scoped lint:

```bash
uv run --with ruff ruff check \
  hermes/plugins/platforms/discord/agk_account_control.py \
  hermes/plugins/platforms/discord/agk_account_usage_monitor.py \
  tests/test_agk_account_control.py tests/test_agk_account_usage_monitor.py
```

```text
All checks passed!
```

Compilation and whitespace verification:

```bash
python3 -m py_compile \
  hermes/plugins/platforms/discord/agk_account_control.py \
  hermes/plugins/platforms/discord/agk_account_usage_monitor.py \
  tests/test_agk_account_control.py tests/test_agk_account_usage_monitor.py
git diff --check -- <the four Task 1 Python paths> task-1-report.md
```

Observed: exit code `0`, no output.

### Self-review

- Secret-shape checks are semantic rather than relying only on a character allowlist.
- The only Discord markdown metacharacter previously admitted by these free-text allowlists, underscore, is now rejected.
- Both Discord roster and provider-panel rendering use the same fail-closed usage-label boundary.
- Existing safe labels and owner names retain their original rendering.
- No unrelated dirty-tree path was edited, staged, reset, reformatted, or committed.
- No reviewer or implementation subagent was spawned, per the explicit task constraint.

### Concerns

None.
