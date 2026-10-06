from django.urls import path

from control.agent_views import (
    EnrollView,
    HeartbeatView,
    OperationClaimView,
    OperationCompleteView,
    OperationProgressView,
    OperationStartedView,
    OperationSourceView,
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
        "operations/<uuid:operation_id>/source",
        OperationSourceView.as_view(),
        name="agent-operation-source",
    ),
    path(
        "operations/<uuid:operation_id>/progress",
        OperationProgressView.as_view(),
        name="agent-operation-progress",
    ),
    path(
        "operations/<uuid:operation_id>/complete",
        OperationCompleteView.as_view(),
        name="agent-operation-complete",
    ),
]
