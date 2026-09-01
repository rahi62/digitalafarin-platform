from rest_framework.routers import DefaultRouter

from .views import AuditEventViewSet, ServerViewSet

router = DefaultRouter()
router.register("servers", ServerViewSet, basename="server")
router.register("audit-events", AuditEventViewSet, basename="audit-event")

urlpatterns = router.urls
