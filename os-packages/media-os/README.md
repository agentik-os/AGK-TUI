# Media OS 1.1.0 (TENANT=AGK)

One Discord Media Director (`media-director`) plus six demand-invoked specialists, running as the dedicated Operator-home Hermes profile `media-os`. Turns one source piece into evidence-backed, platform-native distribution with exact owner approval before any publication.

- `kernel/` — immutable 1.0.0 domain payload (roles, campaign flow, policies, schemas, connector/Discord contracts, Obsidian templates, automations).
- `profile/` — Hermes profile distribution: SOUL, config, 7 agents, 19 ordered skills (17 vendored from charlie947/social-media-skills @ d2e948719eaf, MIT).
- `skills/order.yaml` — binding skill order; `voice-builder` then `newsletter-voice` first; connector-bound skills OWNER_BLOCKED until connected.
- `research/` — Librarian 15-input handoff and ledger.
- `doctor.py`, `rollback.py`, `recovery/` — lifecycle.
