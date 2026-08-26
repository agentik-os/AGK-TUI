# AGK-TUI

AGK-TUI is a clean RMUX control plane for durable AI terminal sessions.
It keeps orchestration independent from any provider while treating the
official [NousResearch Hermes Agent](https://github.com/NousResearch/hermes-agent)
as the primary synchronized agent runtime.

The repository installs:

- RMUX and its required helper layout;
- the native `agk` TUI and persistent session registry;
- Hermes, Claude Code, Codex, OpenCode and Hermes/OpenRouter launch adapters;
- the Agentik OS Hermes plugin, Discord control-center override and Master OS
  Builder catalog agent;
- Composio discovery commands without copying credentials into the repo;
- optional user services for Hermes gateways and headless control.

## Install

### Fresh Debian/Ubuntu VPS

Transfer or clone this repository to a path readable by `operator` (for
example `/opt/AGK-TUI`), inspect the plan, then run the full multi-user
bootstrap:

```bash
sudo ./bootstrap-vps.sh --dry-run
sudo ./bootstrap-vps.sh
```

The bootstrap installs host prerequisites, creates or preserves the
`operator`, `agentik`, `mission`, and `private` Linux users, installs Rust,
RMUX, one shared official Hermes checkout, AGK-TUI, Composio per profile,
the optional Claude/Codex/OpenCode binaries, canonical workspaces and the
TopologyManager timer. `--core-only` skips the optional provider binaries and
`--skip-packages` is available for a pre-provisioned Debian/Ubuntu image.
The default RMUX package is the published `0.10.0` release; an already-running
newer daemon is preserved only when its client passes a real wire-protocol
`list-sessions` check.

Credentials are deliberately never copied. After bootstrap, authenticate only
the profiles that need each service:

```bash
sudo -u mission -H hermes portal
sudo -u mission -H agk composio connect github --no-browser
```

Use `config/hermes.env.example` as the non-secret checklist for a profile.
Install the Hermes gateway only after its Discord token and policy are
configured:

```bash
sudo -u mission -H agk hermes gateway install --force --start-now
```

### Existing host or single profile

```bash
git clone https://github.com/agentik-os/AGK-TUI.git
cd AGK-TUI
./install.sh
```

For a shared binary installation while keeping Hermes data owned by one
non-root identity:

```bash
sudo ./install.sh --system --user "$USER"
```

The default installation keeps user data in `~/.hermes`, `~/.agentik`,
`~/.claude`, `~/.codex`, `~/.config/opencode`, and `~/.composio`. It never
stores provider tokens in the repository.

Useful commands:

```bash
agk                         # native RMUX session control
agk doctor                  # full local readiness report
agk provider list           # installed/configured state
agk provider install claude
agk composio login          # authenticates only the current Linux profile
agk composio connect github # logs in first when needed, then links GitHub
agk composio list           # refresh connected toolkit inventory
agk composio list github    # list GitHub tools
agk hermes sync
agk topology status
```

The TUI's `MCP` view lists every Hermes MCP definition as a parent entry.
Composio is another parent entry; selecting it shows the current profile's
redacted connected-toolkit list and connection states. Refresh it with
`agk composio list` after changing connections.

In the session menu, `Enter` focuses the selected provider immediately and
`x` closes it in one keystroke. `Tab` returns from the provider to the session
list; the persistent footer keeps the active session/project context and the
TKN, RAM, CPU, DISK and LIVE counters visible.

For an exact, irreversible cleanup of one archived AGK registry record and its
RMUX process, use `agk purge --yes SESSION`. Normal `x` uses the recoverable
`agk close` path instead: it stops RMUX and archives the provider history.

On a system install, TopologyManager detects and preserves the four Linux
runtime boundaries while exposing only stable product profile IDs:
`operator`, `agentik`, `mission`, and `private`. It creates missing canonical
workspace directories, writes a non-secret `~/.agentik/profile.yaml` manifest
for each profile, and points `/opt/agentik/hermes/current` at the one official
shared Hermes checkout. Existing extra directories and old recovery releases
are never deleted by this operation.

Composio authentication follows the same boundary: logging in as `operator`
does not authenticate `mission`. Run the command as the intended profile; the
`connect` command starts that profile's login automatically when required:

```bash
sudo -u mission -H /usr/local/bin/agk composio connect github
```

To reinstall or update the shared official Hermes runtime with a recovery
snapshot first:

```bash
sudo agk-terminal hermes install-shared
```

The command creates a timestamped recovery snapshot before changing launchers
or services and preserves every live-session dependency.

`agentik-os.com` is checked as the public Agentik OS availability endpoint.
It is not a Hermes authentication endpoint: official Hermes account and Tool
Gateway authentication remains on Nous Portal, independently for each Linux
profile.

Run the complete local quality gate with `./scripts/test.sh`.

## Design contract

RMUX owns live process/session state. AGK owns durable orchestration metadata.
Official Hermes owns agent behavior, skills, gateways and MCP loading.
AGK-specific behavior is delivered as user plugins and catalog assets, never
by modifying Hermes core.

See [Architecture](docs/ARCHITECTURE.md) and
[shared Hermes runtime](docs/HERMES.md).
