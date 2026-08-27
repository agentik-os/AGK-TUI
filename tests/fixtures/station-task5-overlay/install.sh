# Hermetic semantic fixture for the pre-Task5 Station installer.
install -m 0755 "$repo_root/scripts/agk_provider_oauth_runner.py" "$install_root/scripts/agk_provider_oauth_runner.py"
install -m 0755 "$repo_root/scripts/configure-station-discord-interagent.py" "$install_root/scripts/configure-station-discord-interagent.py"
install -m 0755 "$repo_root/scripts/station_safe_gateway_reload.py" "$install_root/scripts/station_safe_gateway_reload.py"
install -m 0755 "$repo_root/scripts/tailnet_secure_input.py" "$install_root/scripts/tailnet_secure_input.py"
install -m 0755 "$repo_root/scripts/completion_harness.py" "$install_root/scripts/completion_harness.py"
install -m 0755 "$repo_root/scripts/recovery_auditor.py" "$install_root/scripts/recovery_auditor.py"
install -m 0755 "$repo_root/scripts/fleet_recovery_auditor.py" "$install_root/scripts/fleet_recovery_auditor.py"
install -m 0755 "$repo_root/scripts/recovery_router.py" "$install_root/scripts/recovery_router.py"
install -m 0755 "$repo_root/scripts/completion_oracle_gate.py" "$install_root/scripts/completion_oracle_gate.py"
install -m 0755 "$repo_root/scripts/approval_gate.py" "$install_root/scripts/approval_gate.py"
rm -rf "$install_root/hermes/plugins/agk_discord_ui_policy"
cp -a "$repo_root/hermes/plugins/agk_discord_ui_policy" "$install_root/hermes/plugins/"
cp -a "$repo_root/hermes/plugins/platforms/discord" "$install_root/hermes/plugins/platforms/"
cp -a "$repo_root/hermes/agents" "$install_root/agents"
install -m 0644 "$repo_root/systemd/agk-recovery-auditor.service" /etc/systemd/system/agk-recovery-auditor.service
install -m 0644 "$repo_root/systemd/agk-recovery-auditor.timer" /etc/systemd/system/agk-recovery-auditor.timer
install -d -m 0711 /var/lib/station/recovery/approvals
install -d -m 0711 /var/lib/station/recovery/oracle
systemctl enable --now agk-recovery-auditor.timer
