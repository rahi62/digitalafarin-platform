from django.urls import path

from control import control_views, deployment_views, operation_views, telegram_views

urlpatterns = [
    path("projects/", deployment_views.ProjectListCreateView.as_view()),
    path(
        "projects/<uuid:project_id>/services/",
        deployment_views.ProjectServiceListCreateView.as_view(),
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
