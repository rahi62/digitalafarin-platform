import hashlib
import json

from django.db import transaction
from control.models import AuditEvent, Deployment, DeploymentEvent, HealthCheck, Operation, Server, Service, ServiceProvisioning
from control.services.deployments import DeploymentAdmissionError, deployment_admission, apply_deployment_result
from control.services.operations import create_operation


@transaction.atomic
def queue_provisioning(*, project, configuration, actor, idempotency_key):
    data = dict(configuration)
    server = Server.objects.select_for_update().get(pk=data['target_server'].pk)
    snapshot = {key: value for key, value in data.items() if key != 'target_server'}
    fingerprint = hashlib.sha256(json.dumps({'project_id': str(project.public_id), 'server_id': str(server.public_id), **snapshot}, sort_keys=True).encode()).hexdigest()
    previous = Operation.objects.filter(server=server, actor=actor, idempotency_key=idempotency_key).first()
    if previous:
        record = ServiceProvisioning.objects.filter(operation=previous).first()
        if not record or record.request_fingerprint != fingerprint:
            raise DeploymentAdmissionError('Idempotency key already used for a different request.', 'idempotency_conflict')
        return record
    deployment_admission(server)
    if 'service_provision_v1' not in server.capabilities:
        raise DeploymentAdmissionError('Upgrade the Agent and provisioning helper on this server.', 'provisioning_unavailable')
    if Service.objects.filter(project=project, name=data['name']).exists():
        raise DeploymentAdmissionError('A service with this name already exists.', 'duplicate_service')
    if Service.objects.filter(target_server=server, service_port=data['service_port']).exists():
        raise DeploymentAdmissionError('This port is already reserved.', 'port_conflict')
    health_path = data.pop('health_path')
    service = Service(project=project, lifecycle_state='pending', platform_managed=True, **data)
    service.unit_name = f'digitalafarin-app-{service.public_id.hex}.service'
    service.save()
    HealthCheck.objects.create(service=service, path=health_path)
    deployment = Deployment.objects.create(service=service, requested_ref=service.branch, requested_by=actor)
    DeploymentEvent.objects.create(deployment=deployment, state='queued', message='Provisioning queued')
    operation = create_operation(server=server, kind=Operation.KIND_SERVICE_PROVISION,
                                 payload={'deployment_id': str(deployment.public_id)}, actor=actor, idempotency_key=idempotency_key)
    record = ServiceProvisioning.objects.create(service=service, deployment=deployment, operation=operation,
                                                request_fingerprint=fingerprint, configuration=snapshot)
    operation.payload['provisioning_id'] = str(record.public_id)
    operation.save(update_fields=['payload'])
    AuditEvent.objects.create(event_type='provisioning.requested', target_type='service', target_id=str(service.public_id), actor=actor,
                              metadata={'operation_id': str(operation.public_id), 'runtime': service.runtime})
    return record


@transaction.atomic
def apply_provisioning_result(operation, *, succeeded, result, error_code=''):
    record = ServiceProvisioning.objects.select_related('service').get(operation=operation)
    service = Service.objects.select_for_update().get(pk=record.service_id)
    deployment = apply_deployment_result(operation, succeeded=succeeded, result=result, error_code=error_code)
    service.lifecycle_state = 'managed' if succeeded and deployment.state == 'succeeded' else 'provision_failed'
    service.save(update_fields=['lifecycle_state', 'updated_at'])
    AuditEvent.objects.create(event_type='provisioning.succeeded' if service.lifecycle_state == 'managed' else 'provisioning.failed',
                              target_type='service', target_id=str(service.public_id), actor=operation.actor,
                              metadata={'operation_id': str(operation.public_id), 'commit': deployment.resolved_commit})


def serialize_provisioning(record):
    return {'id': str(record.public_id), 'service_id': str(record.service.public_id),
            'deployment_id': str(record.deployment.public_id), 'operation_id': str(record.operation.public_id),
            'state': record.operation.state, 'lifecycle_state': record.service.lifecycle_state}


@transaction.atomic
def retry_provisioning(*, service, actor, idempotency_key):
    server = Server.objects.select_for_update().get(pk=service.target_server_id)
    service = Service.objects.select_for_update().get(pk=service.pk)
    existing = ServiceProvisioning.objects.filter(operation__server=server, operation__actor=actor,
                                                  operation__idempotency_key=idempotency_key).first()
    if existing:
        if existing.service_id != service.pk:
            raise DeploymentAdmissionError('Idempotency key belongs to another service.', 'idempotency_conflict')
        return existing
    if not service.platform_managed or service.lifecycle_state != 'provision_failed':
        raise DeploymentAdmissionError('Only failed provisioning can be retried.', 'retry_unavailable')
    deployment_admission(server)
    prior = service.provisionings.order_by('-created_at').first()
    deployment = Deployment.objects.create(service=service, requested_ref=service.branch, requested_by=actor)
    DeploymentEvent.objects.create(deployment=deployment, state='queued', message='Provisioning retry queued')
    operation = create_operation(server=server, kind=Operation.KIND_SERVICE_PROVISION,
                                 payload={'deployment_id': str(deployment.public_id)}, actor=actor, idempotency_key=idempotency_key)
    record = ServiceProvisioning.objects.create(service=service, deployment=deployment, operation=operation,
                                                request_fingerprint=prior.request_fingerprint, configuration=prior.configuration)
    operation.payload['provisioning_id'] = str(record.public_id)
    operation.save(update_fields=['payload'])
    service.lifecycle_state = 'pending'
    service.save(update_fields=['lifecycle_state', 'updated_at'])
    AuditEvent.objects.create(event_type='provisioning.requested', target_type='service', target_id=str(service.public_id),
                              actor=actor, metadata={'operation_id': str(operation.public_id), 'retry': True})
    return record
