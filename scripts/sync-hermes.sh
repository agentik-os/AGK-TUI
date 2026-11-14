#!/usr/bin/env bash
set -euo pipefail

install_root=${AGK_TERMINAL_ROOT:-/usr/local/lib/agk-terminal}
hermes_home=${HERMES_HOME:-${HOME:?}/.hermes}
case "$hermes_home" in
  ""|/) echo "refusing unsafe HERMES_HOME: ${hermes_home:-<empty>}" >&2; exit 2 ;;
esac
# --all: synchronize the main Hermes home, then every named profile stored
# below it (hermes profile create ...). Profiles stay inside this Linux user.
if [ "${1:-}" = --all ]; then
  self=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/$(basename "${BASH_SOURCE[0]}")
  HERMES_HOME="$hermes_home" "$self"
  for profile_dir in "$hermes_home"/profiles/*/; do
    [ -d "$profile_dir" ] || continue
    HERMES_HOME="${profile_dir%/}" "$self"
  done
  exit 0
fi
[ "$#" -eq 0 ] || { echo "usage: sync-hermes.sh [--all]" >&2; exit 2; }
agent_source=$install_root/agents/master-os-builder
if [ ! -d "$agent_source" ]; then
  agent_source=$install_root/hermes/agents/master-os-builder
fi
agent_target=$hermes_home/agents/master-os-builder
resolve_executable() {
  local path=$1 target
  while [ -L "$path" ]; do
    target=$(readlink "$path")
    case "$target" in
      /*) path=$target ;;
      *) path=$(dirname "$path")/$target ;;
    esac
  done
  printf '%s/%s\n' "$(cd "$(dirname "$path")" && pwd -P)" "$(basename "$path")"
}

hermes_bin=$(resolve_executable "$(command -v hermes)")

mkdir -p "$hermes_home/plugins" "$hermes_home/agents" \
  "$hermes_home/dashboard-themes"
mkdir -p "$HOME/.local/bin"
[ "$hermes_bin" = "$HOME/.local/bin/hermes" ] || ln -sfn "$hermes_bin" "$HOME/.local/bin/hermes"
hermes config migrate >/dev/null
# AGK owns lifecycle health centrally. Routine stop/start chatter is disabled
# on every messaging adapter; the external watchdog emits one Discord #general
# alert only after ten continuous minutes of unavailability.
hermes config set platforms.discord.gateway_restart_notification false >/dev/null
hermes config set platforms.telegram.gateway_restart_notification false >/dev/null
# Keep Discord's stable surface small; evolving actions (including session
# resume) live inside registry-driven Views and therefore need no slash resync.
hermes config set platforms.discord.extra.command_ui_mode ui_only >/dev/null
# Cross-session discovery is intentionally stricter than ordinary bot access:
# Hermes requires an explicit slash administrator. Promote only numeric IDs
# already authorized by the profile's own DISCORD_ALLOWED_USERS setting; never
# copy an identity across Linux/profile boundaries and never print it.
discord_admin_json=$(python3 - "$hermes_home/.env" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
value = ""
try:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("DISCORD_ALLOWED_USERS="):
            value = stripped.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            break
except OSError:
    pass
print(json.dumps([item.strip() for item in value.split(",") if item.strip().isdigit()]))
PY
)
if [ "$discord_admin_json" != "[]" ]; then
  hermes config set platforms.discord.extra.allow_admin_from "$discord_admin_json" >/dev/null
  hermes config set platforms.discord.extra.group_allow_admin_from "$discord_admin_json" >/dev/null
fi
# Content identity of the installed plugins, to tell whether this run
# changed code that a running gateway has already loaded.
plugins_fingerprint() {
  for plugin_path in agentik_os platforms/discord; do
    [ -d "$hermes_home/plugins/$plugin_path" ] || continue
    (cd "$hermes_home/plugins/$plugin_path" &&
      find . -type f ! -name '*.pyc' -exec cksum {} + | sort)
  done | cksum
}
plugins_before=$(plugins_fingerprint)
for plugin_path in agentik_os platforms/discord; do
  plugin_target=$hermes_home/plugins/$plugin_path
  mkdir -p "$(dirname "$plugin_target")"
  rm -rf "$plugin_target.new"
  cp -a "$install_root/hermes/plugins/$plugin_path" "$plugin_target.new"
  rm -rf "$plugin_target"
  mv "$plugin_target.new" "$plugin_target"
done

rm -rf "$agent_target.new"
cp -a "$agent_source" "$agent_target.new"
rm -rf "$agent_target"
mv "$agent_target.new" "$agent_target"

install -m 0644 \
  "$install_root/hermes/dashboard-themes/agentik-shadcn.yaml" \
  "$hermes_home/dashboard-themes/agentik-shadcn.yaml"
install -m 0644 \
  "$install_root/hermes/dashboard-themes/agentik-shadcn-light.yaml" \
  "$hermes_home/dashboard-themes/agentik-shadcn-light.yaml"

for plugin_path in agentik_os platforms/discord; do
  hermes plugins doctor --ci "$hermes_home/plugins/$plugin_path" >/dev/null
done
hermes plugins enable --no-allow-tool-override agentik-os >/dev/null
hermes plugins enable --no-allow-tool-override platforms/discord >/dev/null
hermes skills list --source builtin >/dev/null
rules_python=python3
if ! python3 -c 'import yaml' >/dev/null 2>&1; then
  rules_python=$install_root/venv/bin/python
fi
"$rules_python" "$install_root/scripts/sync-rules.py" >/dev/null
echo "Hermes extensions synchronized in $hermes_home"
# A gateway keeps the plugin code it started with, and slash commands typed
# in a terminal are served by it too. How it is supervised (launchd, systemd,
# by hand) is the owner's choice, so say what is needed instead of guessing.
if [ "$plugins_before" != "$(plugins_fingerprint)" ]; then
  # Captured, not piped: under `pipefail` a `grep -q` that stops reading
  # early makes the whole pipeline fail and the notice would never print.
  gateway_status=$(hermes gateway status 2>/dev/null || true)
  case "$gateway_status" in
    *"is running"*)
      echo "  ! AGK plugins changed: restart the Hermes gateway of $hermes_home to load them"
      ;;
  esac
fi
