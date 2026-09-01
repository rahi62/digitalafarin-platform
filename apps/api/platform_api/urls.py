from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse


def health(_request):
    return JsonResponse({"ok": True, "service": "digitalafarin-platform-api"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
    path("api/", include("control.urls")),
]
