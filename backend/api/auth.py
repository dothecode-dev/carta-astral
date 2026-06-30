from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from api.identity import hash_token
from api.models import Installation


class InstallationTokenAuthentication(BaseAuthentication):
    keyword = b"bearer"

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword:
            return None  # sin header Bearer: que decida el permiso
        if len(auth) != 2:
            raise AuthenticationFailed("invalid bearer header")
        token = auth[1].decode()
        inst = Installation.objects.filter(token_hash=hash_token(token)).first()
        if inst is None:
            raise AuthenticationFailed("invalid token")
        return (inst, inst)

    def authenticate_header(self, request):
        return "Bearer"
