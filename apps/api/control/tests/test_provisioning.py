from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import Operation, Project, Server, Service, ServiceCredential, ServicePrincipal
from control.security import issue_secret


class ProvisioningTests(TestCase):
    def setUp(self):
        self.server = Server.objects.create(name='VPS', last_seen_at=timezone.now(), capabilities=['service_provision_v1'])
        self.project = Project.objects.create(name='Demo', slug='demo')
        principal = ServicePrincipal.objects.create(name='operator', scopes=['operations:create', 'operations:read'])
        token = issue_secret('service')
        ServiceCredential.objects.create(principal=principal, token_prefix=token.prefix, token_hash=token.digest)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.cleartext}')
        self.url = f'/api/control/v1/projects/{self.project.public_id}/services/provision/'
        self.data = dict(name='web', repository='https://github.com/example/demo.git', branch='main',
                         root_directory='.', runtime='node-nextjs', service_port=3000,
                         target_server_id=str(self.server.public_id))

    def provision(self, **overrides):
        return self.client.post(self.url, {**self.data, **overrides}, format='json', HTTP_IDEMPOTENCY_KEY='create-web')

    def test_provision_queues_real_operation_without_claiming_managed(self):
        response = self.provision()
        self.assertEqual(response.status_code, 202)
        service = Service.objects.get()
        self.assertEqual(service.lifecycle_state, 'pending')
        self.assertEqual(service.unit_name, f'digitalafarin-app-{service.public_id.hex}.service')
        self.assertEqual(Operation.objects.get().kind, 'service.provision')
        self.assertEqual(response.json()['service_id'], str(service.public_id))

    def test_same_request_is_idempotent_and_conflicting_reuse_is_rejected(self):
        first = self.provision()
        second = self.provision()
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(self.provision(service_port=3001).status_code, 409)
        self.assertEqual(Service.objects.count(), 1)
        self.assertEqual(Operation.objects.count(), 1)

    def test_invalid_configuration_is_rejected_before_mutation(self):
        for fields in [dict(runtime='python-django'), dict(root_directory='../x'), dict(branch='--upload-pack=x'),
                       dict(repository='https://user:secret@github.com/a/b'), dict(repository='http://127.0.0.1/a'),
                       dict(service_port=80), dict(health_path='//evil.test'), dict(build_configuration={'command': 'id'})]:
            with self.subTest(fields=fields):
                self.assertEqual(self.provision(**fields).status_code, 400)
        self.assertFalse(Service.objects.exists())

    def test_disk_and_server_capability_gate(self):
        self.server.disk_percent = 90
        self.server.save()
        self.assertEqual(self.provision().status_code, 409)
        self.server.disk_percent = 20
        self.server.capabilities = []
        self.server.save()
        self.assertEqual(self.provision().status_code, 409)
        self.assertFalse(Service.objects.exists())

    def test_port_collision_is_rejected(self):
        Service.objects.create(project=self.project, target_server=self.server, name='existing', unit_name='existing.service', service_port=3000)
        self.assertEqual(self.provision().status_code, 409)

    def test_successful_completion_marks_managed_only_after_health_result(self):
        from control.models import AgentCredential, Release
        response = self.provision().json()
        token = issue_secret('agent')
        AgentCredential.objects.create(server=self.server, token_prefix=token.prefix, token_hash=token.digest)
        agent = APIClient()
        agent.credentials(HTTP_AUTHORIZATION=f'Bearer {token.cleartext}')
        claim = agent.post('/api/agent/v1/operations/claim', {}, format='json').json()
        op_id = response['operation_id']
        agent.post(f'/api/agent/v1/operations/{op_id}/started', {'claim_token': claim['claim_token']}, format='json')
        self.assertEqual(Service.objects.get().lifecycle_state, 'provisioning')
        data = {'claim_token': claim['claim_token'], 'succeeded': True, 'result': {
            'deployment_id': response['deployment_id'], 'final_state': 'succeeded',
            'release_name': '20260930-120000-aaaaaaa', 'exact_commit': 'a' * 40,
            'events': [{'state': state} for state in ['preparing', 'cloning', 'building', 'releasing', 'health_check', 'activating', 'verifying', 'succeeded']]}}
        url = f'/api/agent/v1/operations/{op_id}/complete'
        self.assertEqual(agent.post(url, data, format='json').status_code, 200)
        self.assertEqual(agent.post(url, data, format='json').status_code, 200)
        self.assertEqual(Service.objects.get().lifecycle_state, 'managed')
        self.assertEqual(Release.objects.count(), 1)

    def test_failed_completion_never_marks_managed(self):
        from control.models import AgentCredential
        self.provision()
        token = issue_secret('agent')
        AgentCredential.objects.create(server=self.server, token_prefix=token.prefix, token_hash=token.digest)
        agent = APIClient()
        agent.credentials(HTTP_AUTHORIZATION=f'Bearer {token.cleartext}')
        claim = agent.post('/api/agent/v1/operations/claim', {}, format='json').json()
        op_id = claim['operation']['id']
        agent.post(f'/api/agent/v1/operations/{op_id}/started', {'claim_token': claim['claim_token']}, format='json')
        response = agent.post(f'/api/agent/v1/operations/{op_id}/complete',
                              {'claim_token': claim['claim_token'], 'succeeded': False, 'error_code': 'health_failed'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Service.objects.get().lifecycle_state, 'provision_failed')

    def test_failed_service_can_retry_without_duplicate_identity(self):
        self.provision()
        service = Service.objects.get()
        service.lifecycle_state = 'provision_failed'
        service.save()
        Operation.objects.update(state='failed')
        url = f'/api/control/v1/services/{service.public_id}/provision/retry/'
        first = self.client.post(url, {}, format='json', HTTP_IDEMPOTENCY_KEY='retry-web')
        self.assertEqual(first.status_code, 202)
        again = self.client.post(url, {}, format='json', HTTP_IDEMPOTENCY_KEY='retry-web')
        self.assertEqual(first.json(), again.json())
        self.assertEqual(Service.objects.count(), 1)
        self.assertEqual(Operation.objects.count(), 2)
        service.refresh_from_db()
        self.assertEqual(service.lifecycle_state, 'pending')

    def test_rollback_result_reuses_existing_release(self):
        from control.models import Deployment, Release
        from control.services.deployments import apply_deployment_result
        self.provision()
        service = Service.objects.get()
        old = Release.objects.create(service=service, deployment=Deployment.objects.get(), name='20260930-120000-aaaaaaa', exact_commit='a' * 40, path='/unused')
        deployment = Deployment.objects.create(service=service, requested_ref='a' * 40, requested_by='operator')
        operation = Operation.objects.create(server=self.server, kind='deployment.rollback', actor='operator', payload={'deployment_id': str(deployment.public_id)})
        apply_deployment_result(operation, succeeded=True, result={
            'events': [{'state': state} for state in ['preparing', 'cloning', 'building', 'releasing', 'health_check', 'activating', 'verifying', 'succeeded']],
            'final_state': 'succeeded', 'exact_commit': 'a' * 40, 'release_name': old.name,
        })
        deployment.refresh_from_db()
        self.assertEqual(deployment.active_release_id, old.pk)
        self.assertEqual(Release.objects.count(), 1)
