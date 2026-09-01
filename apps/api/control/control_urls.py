from django.urls import path

from control import control_views

urlpatterns = [
    path("servers/", control_views.ServerListView.as_view()),
    path("servers/<str:server_id>/", control_views.ServerDetailView.as_view()),
    path("servers/<str:server_id>/metrics/", control_views.ServerMetricsView.as_view()),
    path("servers/<str:server_id>/services/", control_views.ServiceListView.as_view()),
    path(
        "servers/<str:server_id>/services/<path:unit_name>/",
        control_views.ServiceDetailView.as_view(),
    ),
    path("audit/", control_views.AuditListView.as_view()),
]
