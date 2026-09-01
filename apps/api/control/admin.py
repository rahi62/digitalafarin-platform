from django.contrib import admin

from .models import AuditEvent, Server, ServiceSnapshot

admin.site.register(Server)
admin.site.register(ServiceSnapshot)
admin.site.register(AuditEvent)
