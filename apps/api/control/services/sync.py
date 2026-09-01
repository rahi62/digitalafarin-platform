from django.db import transaction
from django.utils import timezone

from control.models import AuditEvent, Server, ServiceSnapshot
from control.services.agent_client import AgentClient


@transaction.atomic
def sync_server(server: Server, actor: str = "platform-token") -> Server:
    metrics, services = AgentClient(server.agent_url).snapshot()
    now = timezone.now()

    server.cpu_percent = metrics.get("cpu_percent", 0)
    server.memory_percent = metrics.get("memory_percent", 0)
    server.disk_percent = metrics.get("disk_percent", 0)
    server.uptime_seconds = metrics.get("uptime_seconds", 0)
    server.last_seen_at = now
    server.save(update_fields=[
        "cpu_percent", "memory_percent", "disk_percent", "uptime_seconds",
        "last_seen_at", "updated_at",
    ])

    seen_units: set[str] = set()
    for item in services:
        unit_name = item["unit_name"]
        seen_units.add(unit_name)
        ServiceSnapshot.objects.update_or_create(
            server=server,
            unit_name=unit_name,
            defaults={
                "description": item.get("description", ""),
                "load_state": item.get("load_state", "unknown"),
                "active_state": item.get("active_state", "unknown"),
                "sub_state": item.get("sub_state", "unknown"),
            },
        )

    server.services.exclude(unit_name__in=seen_units).delete()

    AuditEvent.objects.create(
        event_type="server.synced",
        target_type="server",
        target_id=str(server.pk),
        actor=actor,
        metadata={"service_count": len(services)},
    )
    return server
