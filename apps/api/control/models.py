from django.db import models


class Server(models.Model):
    name = models.CharField(max_length=120)
    hostname = models.CharField(max_length=255, blank=True)
    agent_url = models.URLField(default="http://127.0.0.1:9743")
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    cpu_percent = models.FloatField(default=0)
    memory_percent = models.FloatField(default=0)
    disk_percent = models.FloatField(default=0)
    uptime_seconds = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name


class ServiceSnapshot(models.Model):
    server = models.ForeignKey(Server, related_name="services", on_delete=models.CASCADE)
    unit_name = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True)
    load_state = models.CharField(max_length=32)
    active_state = models.CharField(max_length=32)
    sub_state = models.CharField(max_length=32)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["server", "unit_name"], name="uniq_server_unit")
        ]
        ordering = ["unit_name"]

    def __str__(self) -> str:
        return f"{self.server.name}: {self.unit_name}"


class AuditEvent(models.Model):
    event_type = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    actor = models.CharField(max_length=120, default="system")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
