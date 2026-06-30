from rest_framework.permissions import BasePermission

from api.models import Installation


class HasInstallation(BasePermission):
    message = "se requiere registro de instalación"

    def has_permission(self, request, view):
        return isinstance(request.auth, Installation)
