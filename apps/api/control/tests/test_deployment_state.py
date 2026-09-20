from django.test import TestCase

from control.models import Deployment, DeploymentEvent, Project, Server, Service
from control.services.deployments import DeploymentTransitionError, transition_deployment


class DeploymentStateTests(TestCase):
    def setUp(self):
        project = Project.objects.create(name="Oily", slug="oily")
        server = Server.objects.create(name="Target")
        service = Service.objects.create(
            project=project,
            name="web",
            unit_name="oily-web.service",
            lifecycle_state=Service.LIFECYCLE_MANAGED,
            repository="https://github.com/example/oily.git",
            branch="main",
            runtime="node-nextjs",
            service_port=3000,
            target_server=server,
        )
        self.deployment = Deployment.objects.create(
            service=service, requested_ref="main", requested_by="operator"
        )

    def test_happy_path_appends_immutable_event_for_each_state(self):
        states = [
            "preparing", "cloning", "building", "releasing", "health_check",
            "activating", "verifying", "succeeded",
        ]
        for state in states:
            transition_deployment(self.deployment.public_id, state, message=state)

        self.deployment.refresh_from_db()
        self.assertEqual(self.deployment.state, "succeeded")
        self.assertEqual(
            list(self.deployment.events.values_list("state", flat=True)), states
        )
        self.assertIsNotNone(self.deployment.started_at)
        self.assertIsNotNone(self.deployment.completed_at)

    def test_illegal_transition_is_rejected_without_event(self):
        with self.assertRaises(DeploymentTransitionError):
            transition_deployment(self.deployment.public_id, "activating")

        self.deployment.refresh_from_db()
        self.assertEqual(self.deployment.state, "queued")
        self.assertEqual(DeploymentEvent.objects.count(), 0)

    def test_failure_and_rolled_back_are_terminal(self):
        transition_deployment(self.deployment.public_id, "preparing")
        transition_deployment(self.deployment.public_id, "failed", failure_code="clone_failed")
        with self.assertRaises(DeploymentTransitionError):
            transition_deployment(self.deployment.public_id, "preparing")

        other = Deployment.objects.create(
            service=self.deployment.service, requested_ref="main", requested_by="operator"
        )
        for state in ["preparing", "cloning", "building", "releasing", "health_check", "activating", "verifying"]:
            transition_deployment(other.public_id, state)
        transition_deployment(other.public_id, "rolled_back", failure_code="health_failed")
        other.refresh_from_db()
        self.assertEqual(other.state, "rolled_back")
