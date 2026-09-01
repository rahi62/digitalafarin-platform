from rest_framework.permissions import BasePermission


def require_scope(scope: str):
    class ScopePermission(BasePermission):
        def has_permission(self, request, view):
            scopes = set(getattr(request.user, "scopes", []))
            return scope in scopes

    ScopePermission.__name__ = f"Require_{scope.replace(':', '_')}"
    return ScopePermission
