import re
import uuid
from datetime import datetime

from django.db import models
from django.db.models import Q
from django.utils import timezone


class Server(models.Model):
    # Keep the integer primary key while legacy pull/sync routes still exist.
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=120)
    hostname = models.CharField(max_length=255, blank=True)
    agent_url = models.URLField(default="http://127.0.0.1:9743")
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    agent_version = models.CharField(max_length=64, blank=True)
    capabilities = models.JSONField(default=list, blank=True)
    cpu_percent = models.FloatField(default=0)
    memory_percent = models.FloatField(default=0)
    disk_percent = models.FloatField(default=0)
    uptime_seconds = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True, is_active=True),
                name="uniq_active_default_server",
            )
        ]

    def age_seconds_at(self, now: datetime | None = None) -> int | None:
        if self.last_seen_at is None:
            return None
        current = now or timezone.now()
        return max(0, int((current - self.last_seen_at).total_seconds()))

    def status_at(self, now: datetime | None = None) -> str:
        age = self.age_seconds_at(now)
        if age is None or age > 120:
            return "offline"
        if age > 45:
            return "stale"
        return "online"

    @property
    def status(self) -> str:
        return self.status_at()

    @property
    def age_seconds(self) -> int | None:
        return self.age_seconds_at()

    @property
    def is_stale(self) -> bool:
        return self.status != "online"

    def __str__(self) -> str:
        return self.name


class EnrollmentToken(models.Model):
    token_prefix = models.CharField(max_length=32, unique=True)
    secret_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)


class AgentCredential(models.Model):
    server = models.ForeignKey(
        Server, related_name="agent_credentials", on_delete=models.CASCADE
    )
    token_prefix = models.CharField(max_length=32, unique=True)
    token_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


class ServicePrincipal(models.Model):
    name = models.CharField(max_length=120, unique=True)
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class ServiceCredential(models.Model):
    principal = models.ForeignKey(
        ServicePrincipal, related_name="credentials", on_delete=models.CASCADE
    )
    token_prefix = models.CharField(max_length=32, unique=True)
    token_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


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


class Operation(models.Model):
    KIND_SERVICE_START = "service.start"
    KIND_SERVICE_STOP = "service.stop"
    KIND_SERVICE_RESTART = "service.restart"
    KIND_SERVICE_LOGS = "service.logs"
    KIND_CHOICES = [
        (KIND_SERVICE_START, "Start service"),
        (KIND_SERVICE_STOP, "Stop service"),
        (KIND_SERVICE_RESTART, "Restart service"),
        (KIND_SERVICE_LOGS, "Read service logs"),
    ]

    STATE_QUEUED = "queued"
    STATE_CLAIMED = "claimed"
    STATE_RUNNING = "running"
    STATE_SUCCEEDED = "succeeded"
    STATE_FAILED = "failed"
    STATE_CHOICES = [
        (STATE_QUEUED, "Queued"),
        (STATE_CLAIMED, "Claimed"),
        (STATE_RUNNING, "Running"),
        (STATE_SUCCEEDED, "Succeeded"),
        (STATE_FAILED, "Failed"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    server = models.ForeignKey(
        Server, related_name="operations", on_delete=models.CASCADE
    )
    kind = models.CharField(max_length=64, choices=KIND_CHOICES)
    state = models.CharField(
        max_length=16, choices=STATE_CHOICES, default=STATE_QUEUED
    )
    payload = models.JSONField(default=dict)
    result = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    actor = models.CharField(max_length=120)
    idempotency_key = models.CharField(max_length=120, blank=True)
    claim_token = models.CharField(max_length=64, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["server", "actor", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_operation_idempotency",
            )
        ]
        indexes = [models.Index(fields=["server", "state", "created_at"])]


class Project(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]


class Service(models.Model):
    EXECUTOR_SYSTEMD = "systemd"
    RUNTIME_NODE = "node-nextjs"
    RUNTIME_DJANGO = "python-django"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey(Project, related_name="services", on_delete=models.CASCADE)
    name = models.SlugField(max_length=80)
    executor = models.CharField(
        max_length=20,
        choices=[(EXECUTOR_SYSTEMD, "Systemd")],
        default=EXECUTOR_SYSTEMD,
    )
    repository = models.URLField(max_length=500)
    branch = models.CharField(max_length=255, default="main")
    root_directory = models.CharField(max_length=255, default=".")
    runtime = models.CharField(
        max_length=32,
        choices=[(RUNTIME_NODE, "Node/Next.js"), (RUNTIME_DJANGO, "Python/Django")],
    )
    install_configuration = models.JSONField(default=dict, blank=True)
    build_configuration = models.JSONField(default=dict, blank=True)
    service_port = models.PositiveIntegerField()
    target_server = models.ForeignKey(
        Server, related_name="managed_services", on_delete=models.PROTECT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="uniq_project_service"
            )
        ]


class HealthCheck(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    service = models.OneToOneField(
        Service, related_name="health_check", on_delete=models.CASCADE
    )
    path = models.CharField(max_length=255, default="/health")
    expected_status = models.PositiveIntegerField(default=200)
    timeout_seconds = models.PositiveIntegerField(default=10)
    interval_seconds = models.PositiveIntegerField(default=5)
    attempts = models.PositiveIntegerField(default=6)


class Deployment(models.Model):
    STATES = [
        (state, state.replace("_", " ").title())
        for state in (
            "queued",
            "preparing",
            "cloning",
            "building",
            "releasing",
            "health_check",
            "activating",
            "verifying",
            "succeeded",
            "failed",
            "rolled_back",
        )
    ]
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    service = models.ForeignKey(
        Service, related_name="deployments", on_delete=models.CASCADE
    )
    requested_ref = models.CharField(max_length=255)
    resolved_commit = models.CharField(max_length=40, blank=True)
    state = models.CharField(max_length=20, choices=STATES, default="queued")
    requested_by = models.CharField(max_length=120)
    source_deployment = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL
    )
    active_release = models.ForeignKey(
        "Release", null=True, blank=True, related_name="active_deployments", on_delete=models.SET_NULL
    )
    previous_release = models.ForeignKey(
        "Release", null=True, blank=True, related_name="rollback_deployments", on_delete=models.SET_NULL
    )
    failure_code = models.CharField(max_length=100, blank=True)
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-queued_at"]


class Release(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    service = models.ForeignKey(Service, related_name="releases", on_delete=models.CASCADE)
    deployment = models.OneToOneField(
        Deployment, related_name="release", on_delete=models.PROTECT
    )
    name = models.CharField(max_length=80)
    exact_commit = models.CharField(max_length=40)
    path = models.CharField(max_length=500)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["service", "name"], name="uniq_service_release")
        ]


class DeploymentEvent(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    deployment = models.ForeignKey(
        Deployment, related_name="events", on_delete=models.CASCADE
    )
    state = models.CharField(max_length=20, choices=Deployment.STATES)
    message = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class EnvironmentVariable(models.Model):
    TYPE_PLAIN = "plain"
    TYPE_SECRET = "secret"
    SCOPE_PROJECT = "project"
    SCOPE_SERVICE = "service"
    SCOPE_ENVIRONMENT = "environment"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey(
        Project, related_name="environment_variables", on_delete=models.CASCADE
    )
    service = models.ForeignKey(
        Service,
        related_name="environment_variables",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    key = models.CharField(max_length=128)
    value_type = models.CharField(
        max_length=10, choices=[(TYPE_PLAIN, "Plain"), (TYPE_SECRET, "Secret")]
    )
    scope = models.CharField(
        max_length=16,
        choices=[
            (SCOPE_PROJECT, "Project"),
            (SCOPE_SERVICE, "Service"),
            (SCOPE_ENVIRONMENT, "Environment"),
        ],
    )
    environment = models.SlugField(max_length=80, blank=True)
    plain_value = models.TextField(blank=True)
    secret_ciphertext = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "key"],
                condition=Q(scope="project"),
                name="uniq_project_variable",
            ),
            models.UniqueConstraint(
                fields=["service", "key"],
                condition=Q(scope="service"),
                name="uniq_service_variable",
            ),
            models.UniqueConstraint(
                fields=["service", "environment", "key"],
                condition=Q(scope="environment"),
                name="uniq_environment_variable",
            ),
        ]


class TelegramBotCredential(models.Model):
    name = models.CharField(max_length=120, unique=True, default="primary")
    is_active = models.BooleanField(default=True)
    token_ciphertext = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TelegramChannel(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    alias = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    chat_id = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    description = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["alias"]

    def save(self, *args, **kwargs):
        alias = (self.alias or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", alias):
            raise ValueError("invalid channel alias")
        self.alias = alias
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.alias}: {self.name}"


class TelegramPublishAudit(models.Model):
    ACTION_TEST = "test"
    ACTION_PUBLISH = "publish"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    channel = models.ForeignKey(
        TelegramChannel,
        related_name="publish_audits",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    action = models.CharField(
        max_length=16,
        choices=[(ACTION_TEST, "Test"), (ACTION_PUBLISH, "Publish")],
    )
    status = models.CharField(
        max_length=16,
        choices=[(STATUS_SUCCESS, "Success"), (STATUS_FAILED, "Failed")],
    )
    message_ids = models.JSONField(default=list, blank=True)
    content_preview = models.CharField(max_length=280, blank=True)
    content_sha256 = models.CharField(max_length=64, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    actor_principal = models.CharField(max_length=120, default="system")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
