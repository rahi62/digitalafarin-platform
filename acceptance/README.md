# Migration readiness fixture

Run the safe disposable migration workflow from the repository root:

```bash
PYTHONPATH=.:agent apps/api/.venv/bin/python apps/api/manage.py test acceptance.test_migration_readiness -v 2
```

The fixture uses temporary directories, a local Git repository, mocked systemd,
PostgreSQL, and health boundaries, and never contacts or restarts production
services.

Deployment and rollback use a disposable helper-interface double with real local
Git checkout and Node fixture builds. It verifies helper-bound identity and
activation/pruning requests; it does not validate privileged helper ownership,
sealing, systemd, or worker isolation. Those boundaries are covered by the agent
suite and its disposable Linux integration tests. Managed environment and volume
updates remain unsupported and are explicitly asserted to fail before preparation.
The Platform CI API job runs this fixture alongside the complete Control Plane suite.
