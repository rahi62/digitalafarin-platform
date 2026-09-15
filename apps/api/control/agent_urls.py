from django.urls import path

from control.agent_views import (
    EnrollView,
    HeartbeatView,
    OperationClaimView,
    OperationCompleteView,
    OperationStartedView,
)

urlpatterns = [
    path("enroll", EnrollView.as_view(), name="agent-enroll"),
    path("heartbeat", HeartbeatView.as_view(), name="agent-heartbeat"),
    path("operations/claim", OperationClaimView.as_view(), name="agent-operation-claim"),
    path(
        "operations/<uuid:operation_id>/started",
        OperationStartedView.as_view(),
        name="agent-operation-started",
    ),
    path(
        "operations/<uuid:operation_id>/complete",
        OperationCompleteView.as_view(),
        name="agent-operation-complete",
    ),
]
