from rest_framework.permissions import BasePermission

from api.models import Account


class HasAccount(BasePermission):
    message = "se requiere autenticación con cuenta"

    def has_permission(self, request, view):
        return isinstance(request.auth, Account)
