from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(_request):
    return JsonResponse({"ok": True, "service": "digitalafarin-platform-api"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
    path("api/agent/v1/", include("control.agent_urls")),
    path("api/", include("control.urls")),
]
