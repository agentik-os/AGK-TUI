# Setup

Media OS packages install immutably side-by-side and remain `INACTIVE`. `scripts/install.py` requires an explicit offline root and source and establishes only offline lifecycle records; it never assigns or activates. The scripts locate the repository runtime from their committed package location, so direct `python3 .../scripts/<name>.py --help` works without ambient `PYTHONPATH`.

Activation is available only through Task 5's `ProvisioningLifecycleCoordinator`, configured with the canonical `ProvisionPlan`, concrete OSRegistry/package, profile/transaction, assignment, route, connector, job, board/dispatcher, and knowledge adapters, concrete doctor probes, and a smoke check. Authority is an unexported object created only while that coordinator holds its kernel lock; it never leaves the coordinator. The same mutation window spans snapshot/readback, the real `apply_provision_plan` boundary, doctor, switch, and smoke. No path, seal, constructor, callback, or serialized token can issue activation authority.

## Media Director gateway handoff

`systemd/hermes-gateway-media-os.service` is a deployment template for the Media Director profile only. Package installation may copy the reviewed unit and reload the user-service manager, but the deployment contract requires the unit to remain disabled and inactive until the owner completes onboarding. Package installation and automation registration must not enable, start, or restart it.

The owner creates the bot/application identity and supplies a freshly rotated token through hidden stdin or Tailnet Secure Input. The onboarding boundary must validate the bot identity, exact channel allowlist, and required intents with read-only calls before writing the Media Director profile `.env` as mode `0600`. It may then enable and start only `hermes-gateway-media-os.service`; it must not restart another gateway or post a channel restart notice. The unit contains no token value and reads only the profile-local `.env`.

The five automation files under `templates/automation` are disabled registration templates. A later owner-approved deployment may register them, but they must remain bounded, no-change silent, non-publishing, and recovery alerts must target the owner DM only.
