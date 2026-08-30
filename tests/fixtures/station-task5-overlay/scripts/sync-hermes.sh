#!/usr/bin/env bash
agent_source_root=$install_root/agents
for plugin_path in agentik_os agk_discord_ui_policy platforms/discord; do :; done
for agent_source in "$agent_source_root"/*; do :; done
hermes config set platforms.discord.extra.account_control_enabled true
hermes config set platforms.discord.extra.account_control_category_id 1542505218569150585
hermes config set platforms.discord.extra.account_control_owner_user_id 1441423462492016821
hermes config set platforms.discord.extra.account_control_channel_name account-control
hermes config set platforms.discord.extra.account_control_oauth_timeout_seconds 900
hermes plugins enable --no-allow-tool-override agk-discord-ui-policy
