# Hermetic semantic fixture; legacy text panels are intentionally absent.
from .agk_account_control import AliasRegistry, voice_binding_key

class DiscordAccountUsageMonitor:
    async def refresh_once(self):
        return None
