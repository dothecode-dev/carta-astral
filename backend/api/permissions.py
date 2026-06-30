from rest_framework.permissions import BasePermission

from api.models import Account, Installation


class HasInstallation(BasePermission):
    message = "se requiere registro de instalación"

    def has_permission(self, request, view):
        return isinstance(request.auth, Installation)


class HasAccount(BasePermission):
    message = "se requiere autenticación con cuenta"

    def has_permission(self, request, view):
        return isinstance(request.auth, Account)
