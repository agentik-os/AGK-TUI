# First campaign: offline acceptance

This fixture proves the complete Media OS loop without credentials, network access, live Discord, services, containers, brokers, gateway activation, or external publication.

## Run

```bash
python3 scripts/verify_media_os.py --offline --json /tmp/media-os-offline-verification.json
```

Use the project test environment described in the repository when invoking the command. A successful report contains twelve offline `PASS` gates and two `OWNER_BLOCKED` live-authorization gates.

## Fixture

The campaign source is `tests/fixtures/media_os/first_campaign/source.md`; `campaign.json` binds it by SHA-256. The deterministic rig uses local fake Kanban, Discord principal/callback, connector, provider, and Obsidian ports. It records one revision request, one exact owner approval, one successful publication readback, one fixed-age observation, one non-promoted hypothesis, one correction simulation, and one rollback. Unsupported scale claims are absent from public artifact text.

## Lifecycle witness

The verifier uses isolated temporary roots only. It performs canonical Task 5 provisioning with a filesystem-backed fake Hermes runner, validates dimension-specific resource schemas through exact readbacks, installs the real package in an isolated registry, obtains a truthful twelve-of-twelve doctor result, activates to `ACTIVE`, then proves rollback and restore postconditions. Synthetic status envelopes are not accepted.

## Live refusal

`--live` performs no mutation. Missing explicit Discord and platform target IDs or a readable approval artifact is a hard refusal. Even when prerequisites are supplied, Task 13 remains prerequisite-check-only and returns `OWNER_BLOCKED`; live activation/publication belongs to later owner-authorized tasks.
