import importlib
from types import SimpleNamespace

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase


class ServiceAdoptionMigrationTests(TransactionTestCase):
    migrate_from = [("control", "0013_domains")]
    migrate_to = [("control", "0014_service_adoption")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Server = old_apps.get_model("control", "Server")
        Project = old_apps.get_model("control", "Project")
        Service = old_apps.get_model("control", "Service")
        server = Server.objects.create(name="Target")
        project = Project.objects.create(name="Oily", slug="oily")
        self.service_pk = Service.objects.create(
            project=project,
            name="web",
            executor="systemd",
            repository="https://github.com/example/oily.git",
            branch="main",
            root_directory=".",
            runtime="node-nextjs",
            install_configuration={},
            build_configuration={},
            service_port=3000,
            target_server=server,
        ).pk
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_service_is_backfilled_as_managed_with_old_unit_name(self):
        Service = self.apps.get_model("control", "Service")
        service = Service.objects.get(pk=self.service_pk)
        self.assertEqual(service.lifecycle_state, "managed")
        self.assertEqual(service.unit_name, "oily-web.service")
        self.assertEqual(service.repository, "https://github.com/example/oily.git")
        self.assertEqual(service.runtime, "node-nextjs")
        self.assertEqual(service.service_port, 3000)


class ServiceAdoptionMigrationPreflightTests(SimpleTestCase):
    def test_duplicate_preflight_rejects_same_server_unit_binding(self):
        migration = importlib.import_module("control.migrations.0014_service_adoption")
        rows = [
            SimpleNamespace(
                target_server_id=1,
                project=SimpleNamespace(slug="oily"),
                name="web",
            ),
            SimpleNamespace(
                target_server_id=1,
                project=SimpleNamespace(slug="oily"),
                name="web",
            ),
        ]
        with self.assertRaisesMessage(RuntimeError, "duplicate service unit binding"):
            migration._assert_unique_bindings(rows)
