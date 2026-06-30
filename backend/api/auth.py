from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from api.identity import hash_token, new_token
from api.models import Session


def create_session(account) -> str:
    clear, token_hash = new_token()
    Session.objects.create(
        token_hash=token_hash, account=account,
        expires_at=timezone.now() + timezone.timedelta(days=settings.SESSION_TTL_DAYS),
    )
    return clear


class AccountTokenAuthentication(BaseAuthentication):
    keyword = b"bearer"

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword:
            return None
        if len(auth) != 2:
            raise AuthenticationFailed("invalid bearer header")
        token = auth[1].decode()
        session = Session.objects.filter(token_hash=hash_token(token)).select_related("account").first()
        if session is None:
            raise AuthenticationFailed("invalid token")
        if session.expires_at <= timezone.now():
            raise AuthenticationFailed("session expired")
        return (session.account, session.account)

    def authenticate_header(self, request):
        return "Bearer"
