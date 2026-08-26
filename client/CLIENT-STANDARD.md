# AGK Client Organization Standard

Standard version: `1`

Every client is an isolated product organization inside the `mission` profile.
The Linux username is a runtime boundary; AGK business objects use the stable
client id from `.client/manifest.yaml`.

## Sources of truth

- Linear owns product work, status, scope and decision history.
- GitHub owns code, branches, commits, pull requests and CI evidence.
- Figma owns product design when the client uses it.
- Hermes owns agent execution and resumable conversation state.
- The client runtime owns staging and production execution.
- Discord is the human decision interface, never the work database.
- AGK owns orchestration, policy checks, audit records and identity mapping.

## Mandatory delivery invariant

```text
NO LINEAR ISSUE
    -> NO CODING
    -> NO COMMIT
    -> NO PULL REQUEST
    -> NO DEPLOYMENT
```

Every work record preserves the same client, Linear issue, repository, branch,
mission id and Hermes session throughout revisions. `REQUEST CHANGES` resumes
that existing context; it must not silently create a fresh agent session.

## Client boundary

```text
workspace/clients/<slug>/
├── README.md
├── CLIENT.md
├── AGENTS.md
├── CLAUDE.md
├── .client/
│   ├── manifest.yaml
│   ├── runtime.yaml
│   ├── integrations.yaml
│   ├── permissions.yaml
│   ├── workflow.yaml
│   └── team.yaml
├── repos/
├── knowledge/
├── projects/
├── artifacts/
├── deployments/
├── infrastructure/
├── automation/
├── scripts/
├── logs/
├── state/
│   ├── work/
│   ├── reviews/
│   └── runs/
└── tmp/
```

Secrets never live in that tree. The only supported local secret store is:

```text
~/.config/agk/clients/<slug>/env
```

It is owned by the current profile and has mode `0600`. Composio OAuth tokens
remain in Composio's profile-local store; client configs contain only account
aliases such as `client-<slug>-linear`.

## Logical team

The team definition is logical and cheap. Roles are instantiated on demand,
not kept alive as permanent processes. The standard roster covers Product,
Engineering, Platform, Security, QA, Release, Observability, FinOps and Design.
Every runtime session is tagged with `client`, `project`, `mission`, role and
Linear issue metadata.

## Workflow and human gates

The standard flow is:

```text
TODO -> IN_PROGRESS -> AGENT_REVIEW -> AUTOMATED_QA -> READY_FOR_CTO
     -> CTO_APPROVED -> READY_TO_DEPLOY -> PRODUCTION -> VERIFIED -> DONE
```

`CTO_APPROVED` means the engineering result is accepted.
`READY_TO_DEPLOY` requires a separate production authorization. A production
action without that second approval is rejected even when engineering was
already approved.

## Policy levels

- L0: read-only inspection.
- L1: branch and development changes tied to a Linear issue.
- L2: staging actions with evidence.
- L3: production actions requiring explicit human authorization.
- L4: critical operations; destructive database deletion is forbidden and
  other critical actions always require a CTO authorization.

Every infrastructure action becomes an immutable AGK Run record containing the
actor, machine, action, before/after versions, issue, commit, timestamps,
result, evidence and rollback availability.

## Integrations

Client integrations are selected through stable, non-secret aliases. A client
must never fall back to another account merely because it is the profile's
default connection. The expected aliases are recorded in
`.client/integrations.yaml` and verified before external actions.

Discord supports a shared CTO Command Center or a dedicated client bot. The
default is a shared command center with client-scoped categories/channels and
explicit connection aliases. Provisioning is dry-run first, idempotent and
must roll back resources created by a failed apply.

Linear webhooks are accepted only when the HMAC-SHA256 signature over the raw
request body is valid and `webhookTimestamp` is within the configured replay
window. Webhook secrets are never written to the client workspace.

## Installation contract

`agk client bootstrap` installs this standard without provisioning a client.
`agk client init` performs local, transactional scaffolding only. External
resources are planned and verified separately; creation requires an explicit
apply command and human confirmation.
