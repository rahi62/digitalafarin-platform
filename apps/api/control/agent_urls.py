from django.urls import path

from control.agent_views import EnrollView, HeartbeatView

urlpatterns = [
    path("enroll", EnrollView.as_view(), name="agent-enroll"),
    path("heartbeat", HeartbeatView.as_view(), name="agent-heartbeat"),
]
