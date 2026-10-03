# Platform one-time bootstrap upgrade

This procedure exists only to cross the bootstrap boundary where the currently running Agent and privileged helper predate operation-bound GitHub source transport.

## Preconditions

- Run only on the production host as root.
- Production repository must be `/opt/digitalafarin-platform`.
- The repository must have no local tracked changes.
- Use an exact lowercase 40-character commit that has passed CI.
- Keep GitHub App credentials only in `/etc/digitalafarin-platform/api.env`; never pass them as script arguments.

Required API environment for GitHub source transport and signed push webhooks:

```dotenv
GITHUB_APP_ID=...
GITHUB_APP_PRIVATE_KEY=...
GITHUB_APP_WEBHOOK_SECRET=...
```

The GitHub App installation must grant the selected repository `Contents: read`. Configure its push webhook to the existing Control Plane GitHub webhook endpoint.

## Upgrade

After reviewing the target commit and CI:

```bash
sudo bash /opt/digitalafarin-platform/infra/bootstrap-platform-upgrade.sh <exact-commit>
```

The script has a fixed production repository, validates the repository origin and exact commit, refuses local tracked changes, installs dependencies into the existing venvs, checks and applies committed Django migrations, runs Web tests/lint/build, installs only reviewed Platform unit files, restarts Helper → API → Agent → MCP → Web, and verifies API health.

It deliberately does not modify tunnel ownership, credentials, Nginx, PostgreSQL, deployment releases, or unrelated services.

## Verification

After success verify through the Control Plane/MCP:

- server online and heartbeat fresh;
- Agent version/capabilities updated as expected;
- all five Platform services active;
- disk remains below the deployment hard-block threshold;
- service settings expose Auto Deploy;
- a signed GitHub push to an enabled service queues exactly one deployment per matching service;
- the deployment downloads an operation-bound Git bundle, verifies the exact commit, builds an immutable release, activates it, and passes health verification.

This script is a bootstrap bridge, not the long-term deployment mechanism. Normal application deployments continue through typed operations and immutable releases.
