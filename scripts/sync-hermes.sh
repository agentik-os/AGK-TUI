#!/usr/bin/env bash
set -euo pipefail

install_root=${AGK_TERMINAL_ROOT:-/usr/local/lib/agk-terminal}
hermes_home=${HERMES_HOME:-${HOME:?}/.hermes}
case "$hermes_home" in
  ""|/) echo "refusing unsafe HERMES_HOME: ${hermes_home:-<empty>}" >&2; exit 2 ;;
esac
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

mkdir -p "$hermes_home/plugins" "$hermes_home/agents"
mkdir -p "$HOME/.local/bin"
ln -sfn "$hermes_bin" "$HOME/.local/bin/hermes"
hermes config migrate >/dev/null
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

for plugin_path in agentik_os platforms/discord; do
  hermes plugins doctor --ci "$hermes_home/plugins/$plugin_path" >/dev/null
done
hermes plugins enable --no-allow-tool-override agentik-os >/dev/null
hermes plugins enable --no-allow-tool-override platforms/discord >/dev/null
hermes skills list --source builtin >/dev/null
echo "Hermes extensions synchronized in $hermes_home"
