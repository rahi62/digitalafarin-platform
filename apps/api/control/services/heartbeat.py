from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from control.models import AuditEvent, Server, ServiceSnapshot


@transaction.atomic
def apply_heartbeat(server: Server, payload: dict) -> Server:
    now = timezone.now()
    metrics = payload["metrics"]
    server.hostname = payload["hostname"]
    server.agent_version = payload["agent_version"]
    server.capabilities = payload["capabilities"]
    server.cpu_percent = metrics["cpu_percent"]
    server.memory_percent = metrics["memory_percent"]
    server.disk_percent = metrics["disk_percent"]
    server.uptime_seconds = metrics["uptime_seconds"]
    server.last_seen_at = now
    server.save(
        update_fields=[
            "hostname",
            "agent_version",
            "capabilities",
            "cpu_percent",
            "memory_percent",
            "disk_percent",
            "uptime_seconds",
            "last_seen_at",
            "updated_at",
        ]
    )

    seen: set[str] = set()
    for item in payload["services"]:
        seen.add(item["unit_name"])
        ServiceSnapshot.objects.update_or_create(
            server=server,
            unit_name=item["unit_name"],
            defaults={
                "description": item.get("description", ""),
                "load_state": item["load_state"],
                "active_state": item["active_state"],
                "sub_state": item["sub_state"],
            },
        )
    server.services.exclude(unit_name__in=seen).delete()

    recent = AuditEvent.objects.filter(
        event_type="agent.heartbeat.accepted",
        target_type="server",
        target_id=str(server.public_id),
        created_at__gte=now - timedelta(minutes=5),
    ).exists()
    if not recent:
        AuditEvent.objects.create(
            event_type="agent.heartbeat.accepted",
            target_type="server",
            target_id=str(server.public_id),
            actor=f"agent:{server.public_id}",
            metadata={"service_count": len(seen)},
        )
    return server
