#!/usr/bin/env bash
set -euo pipefail

if [ -z "${AGK_TERMINAL_ROOT:-}" ] && [ -d "$HOME/.local/lib/agk-terminal" ]; then
  AGK_TERMINAL_ROOT=$HOME/.local/lib/agk-terminal
fi
install_root=${AGK_TERMINAL_ROOT:-/usr/local/lib/agk-terminal}
failed=0
# PyYAML lives in AGK's own environment, not in the system Python.
python=$install_root/venv/bin/python
[ -x "$python" ] || python=python3
hermes_home=${HERMES_HOME:-$HOME/.hermes}
export PATH="$HOME/.local/bin:$install_root/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

check() {
  local name=$1
  shift
  if "$@" >/dev/null 2>&1; then
    printf '✓ %s\n' "$name"
  else
    printf '✗ %s\n' "$name"
    failed=1
  fi
}

# A provider, account or service the user chose not to set up is reported
# without failing the health check of everything that is installed.
note() {
  local name=$1
  shift
  if "$@" >/dev/null 2>&1; then
    printf '✓ %s\n' "$name"
  else
    printf '· %s (not set up)\n' "$name"
  fi
}

discord_connected() {
  "$python" - "$hermes_home/gateway_state.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    state = json.load(handle)
discord = state.get("platforms", {}).get("discord", {})
raise SystemExit(
    0
    if state.get("gateway_state") == "running"
    and discord.get("state") == "connected"
    and not discord.get("error_code")
    else 1
)
PY
}

composio_authenticated() {
  "$python" - "$HOME/.composio/user_data.json" <<'PY'
import json
import sys

try:
    value = json.load(open(sys.argv[1], encoding="utf-8")).get("api_key")
except (OSError, ValueError, AttributeError):
    raise SystemExit(1)
raise SystemExit(0 if isinstance(value, str) and value.strip() else 1)
PY
}

portal_authenticated() {
  hermes portal info 2>/dev/null | grep -F '✓ logged in' >/dev/null
}

portal_ready_for_selected_provider() {
  local provider
  provider=$("$python" - "$hermes_home/config.yaml" <<'PY'
import sys
import yaml

try:
    config = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
except (OSError, ValueError, TypeError):
    raise SystemExit(1)
model = config.get("model") or {}
print(str(model.get("provider") or "nous").strip().lower())
PY
  ) || return 1
  [ "$provider" != nous ] || portal_authenticated
}

check 'RMUX binary' rmux -V
rmux_ready() {
  local output
  output=$(rmux list-sessions 2>&1) && return 0
  # No daemon yet is healthy: RMUX starts one with the first session.
  case "$output" in
    *"no server running on "*|*"error connecting to "*"(No such file or directory)"*) return 0 ;;
  esac
  return 1
}
check 'RMUX client and daemon' rmux_ready
check 'AGK TUI' test -x "$install_root/bin/agk-tui"
check 'AGK controller' test -x "$install_root/scripts/agk_control.py"
check 'Global rules registry' test -r "$install_root/config/rules.yaml"
check 'AGK Python environment' "$python" -c 'import yaml'
check 'AGK launcher on PATH' command -v agk

echo
echo 'Optional providers, accounts and services:'
note 'Claude global rules' grep -Fq '<!-- AGK MANAGED RULES: START -->' "$HOME/.claude/CLAUDE.md"
note 'Codex global rules' grep -Fq '<!-- AGK MANAGED RULES: START -->' "$HOME/.codex/AGENTS.md"
note 'OpenCode global rules' grep -Fq '<!-- AGK MANAGED RULES: START -->' "$HOME/.config/opencode/AGENTS.md"
note 'Hermes plugin' hermes plugins doctor --ci "$hermes_home/plugins/agentik_os"
note 'AGK Discord plugin' hermes plugins doctor --ci "$hermes_home/plugins/platforms/discord"
note 'Master OS Builder' test -f "$hermes_home/agents/master-os-builder/agent.yaml"
note 'Official Hermes' "$install_root/scripts/provider.sh" verify hermes
note 'Hermes configuration' hermes config check
note 'Nous Portal authentication (when selected)' portal_ready_for_selected_provider
note 'Discord gateway' discord_connected
note 'Agentik OS cloud' curl -fsSIL --max-time 10 https://agentik-os.com
note 'Chrome browser engine' google-chrome --version
note 'Claude Code' "$install_root/scripts/provider.sh" verify claude
note 'Codex' "$install_root/scripts/provider.sh" verify codex
note 'OpenCode' "$install_root/scripts/provider.sh" verify opencode
note 'OpenRouter' "$install_root/scripts/provider.sh" verify openrouter
note 'Composio CLI' composio --version
note 'Composio authentication' composio_authenticated

"$install_root/scripts/provider.sh" list
exit "$failed"
