from django.urls import path

from control import (
    control_views,
    database_views,
    domain_views,
    deployment_views,
    environment_views,
    github_views,
    operation_views,
    telegram_views,
    takeover_views,
    volume_views,
)

urlpatterns = [
    path(
        "services/<uuid:service_id>/takeovers/",
        takeover_views.ServiceTakeoverListCreateView.as_view(),
    ),
    path(
        "takeovers/<uuid:takeover_id>/",
        takeover_views.TakeoverDetailView.as_view(),
    ),
    path(
        "takeovers/<uuid:takeover_id>/activate/",
        takeover_views.TakeoverActivateView.as_view(),
    ),
    path(
        "takeovers/<uuid:takeover_id>/cancel/",
        takeover_views.TakeoverCancelView.as_view(),
    ),
    path("github/webhook/", github_views.GitHubWebhookView.as_view()),
    path("projects/<uuid:project_id>/", deployment_views.ProjectDetailView.as_view()),
    path(
        "servers/<uuid:server_id>/bootstrap/",
        deployment_views.ServerBootstrapView.as_view(),
    ),
    path("projects/", deployment_views.ProjectListCreateView.as_view()),
    path(
        "projects/<uuid:project_id>/services/",
        deployment_views.ProjectServiceListCreateView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/services/adopt/",
        deployment_views.ProjectServiceAdoptView.as_view(),
    ),
    path(
        "services/<uuid:service_id>/deployment-configuration/",
        deployment_views.ServiceDeploymentConfigurationView.as_view(),
    ),
    path(
        "services/<uuid:service_id>/deployments/",
        deployment_views.ServiceDeploymentListCreateView.as_view(),
    ),
    path(
        "deployments/<uuid:deployment_id>/redeploy/",
        deployment_views.DeploymentRedeployView.as_view(),
    ),
    path(
        "deployments/<uuid:deployment_id>/rollback/",
        deployment_views.DeploymentRollbackView.as_view(),
    ),
    path(
        "deployments/<uuid:deployment_id>/",
        deployment_views.DeploymentDetailView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/variables/",
        environment_views.EnvironmentVariableListCreateView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/volumes/",
        volume_views.VolumeListCreateView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/databases/",
        database_views.DatabaseListCreateView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/domains/",
        domain_views.DomainListCreateView.as_view(),
    ),
    path("domains/<uuid:domain_id>/ssl/", domain_views.DomainSSLView.as_view()),
    path(
        "databases/<uuid:database_id>/restore/",
        database_views.DatabaseRestoreView.as_view(),
    ),
    path("operations/", operation_views.OperationListCreateView.as_view()),
    path(
        "operations/<uuid:operation_id>/",
        operation_views.OperationDetailView.as_view(),
    ),
    path("servers/", control_views.ServerListView.as_view()),
    path("servers/<str:server_id>/", control_views.ServerDetailView.as_view()),
    path("servers/<str:server_id>/metrics/", control_views.ServerMetricsView.as_view()),
    path("servers/<str:server_id>/services/", control_views.ServiceListView.as_view()),
    path(
        "servers/<str:server_id>/services/<path:unit_name>/",
        control_views.ServiceDetailView.as_view(),
    ),
    path("audit/", control_views.AuditListView.as_view()),
    path("telegram/status/", telegram_views.TelegramStatusView.as_view()),
    path("telegram/bot-credential/", telegram_views.TelegramBotCredentialView.as_view()),
    path("telegram/channels/", telegram_views.TelegramChannelListView.as_view()),
    path(
        "telegram/channels/<uuid:channel_id>/",
        telegram_views.TelegramChannelDetailView.as_view(),
    ),
    path(
        "telegram/channels/<uuid:channel_id>/test/",
        telegram_views.TelegramChannelTestView.as_view(),
    ),
    path("telegram/audit/", telegram_views.TelegramAuditListView.as_view()),
    path("telegram/publish/", telegram_views.TelegramPublishView.as_view()),
]
