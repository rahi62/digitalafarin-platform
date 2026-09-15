# Migration readiness fixture

Run the safe disposable migration workflow from the repository root:

```bash
PYTHONPATH=.:agent apps/api/.venv/bin/python apps/api/manage.py test acceptance.test_migration_readiness -v 2
```

The fixture uses temporary directories, a local Git repository, mocked systemd,
PostgreSQL, and health boundaries, and never contacts or restarts production
services.
