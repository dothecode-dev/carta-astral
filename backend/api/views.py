import logging

from django.conf import settings
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.exceptions import CoreError
from interpret.exceptions import InterpretationError

from api import geocode
from api.accounts import resolve_account
from api.auth import (
    AccountTokenAuthentication,
    InstallationTokenAuthentication,
    create_session,
)
from api.chart_service import create_chart
from api.identity import new_token
from api.interpretation_service import (
    DISCLAIMERS,
    CapReached,
    QuotaExceeded,
    get_or_create_interpretation,
)
from api.ledger import credits_available as account_credits_available
from api.models import Chart, Installation, Interpretation
from api.permissions import HasAccount, HasInstallation
from api.sso import SSONotConfigured, SSOError, validate_apple, validate_google

logger = logging.getLogger(__name__)

_INTERPRETATION_LANGS = ("es", "en", "pt")


class InstallationCreateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "install"

    def post(self, request):
        clear, token_hash = new_token()
        Installation.objects.create(token_hash=token_hash)
        return Response(
            {"token": clear, "credits_available": settings.INSTALL_FREE_CREDITS},
            status=status.HTTP_201_CREATED,
        )


class InstallationMeView(APIView):
    authentication_classes = [InstallationTokenAuthentication]
    permission_classes = [HasInstallation]

    def get(self, request):
        inst = request.auth
        used = Interpretation.objects.filter(installation=inst).count()
        avail = settings.INSTALL_FREE_CREDITS + inst.purchased_credits - used
        return Response({"credits_available": avail})


class AccountMeView(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request):
        return Response({
            "credits_available": account_credits_available(request.user),
            "account_id": request.user.id,
        })


def _chart_repr(chart: Chart) -> dict:
    return {
        "id": str(chart.uuid),
        "house_system": chart.house_system,
        "zodiac": chart.zodiac,
        "data": chart.data,
        "engine_version": chart.engine_version,
    }


class ChartCreateView(APIView):
    def post(self, request):
        try:
            chart = create_chart(request.data)
        except (KeyError, ValueError, CoreError) as exc:
            logger.warning("chart creation rejected: %s", exc, exc_info=True)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_chart_repr(chart), status=status.HTTP_201_CREATED)


class ChartDetailView(APIView):
    def get(self, request, uuid):
        chart = get_object_or_404(Chart, uuid=uuid)
        return Response(_chart_repr(chart))


class GeocodeView(APIView):
    def post(self, request):
        q = request.data.get("q", "")
        try:
            results = geocode.search(q)
        except ValueError as exc:
            logger.warning("geocode query rejected: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"results": results})


class InterpretationView(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "interpretation"

    def post(self, request, uuid):
        lang = request.data.get("lang", "es")
        if lang not in _INTERPRETATION_LANGS:
            return Response(
                {"error": f"lang debe ser uno de {_INTERPRETATION_LANGS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        chart = get_object_or_404(Chart, uuid=uuid)
        try:
            interp = get_or_create_interpretation(chart, lang, request.user)
        except QuotaExceeded:
            return Response(
                {"error": "sin créditos disponibles"},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        except CapReached:
            return Response(
                {"error": "límite diario de interpretaciones alcanzado, probá más tarde"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except InterpretationError as exc:
            logger.warning("interpretation generation failed: %s", exc, exc_info=True)
            return Response(
                {"error": "no se pudo generar la interpretación"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {
                "text": interp.text,
                "lang": interp.lang,
                "prompt_version": interp.prompt_version,
                "disclaimer": DISCLAIMERS[interp.lang],
                "created_at": interp.created_at.isoformat(),
            }
        )


class _BaseAuthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"
    validator = None  # set por subclase

    def post(self, request):
        id_token = request.data.get("id_token")
        if not id_token:
            return Response({"error": "id_token requerido"}, status=status.HTTP_400_BAD_REQUEST)
        nonce = request.data.get("nonce")
        try:
            vid = self.validator(id_token, nonce=nonce)
        except SSONotConfigured as exc:
            logger.error("SSO no configurado: %s", exc)
            return Response({"error": "login no disponible"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except SSOError as exc:
            logger.warning("id_token inválido: %s", exc)
            return Response({"error": "token inválido"}, status=status.HTTP_401_UNAUTHORIZED)
        account = resolve_account(vid)
        token = create_session(account)
        return Response({
            "token": token,
            "credits_available": account_credits_available(account),
            "account_id": account.id,
        })


class AppleAuthView(_BaseAuthView):
    def validator(self, id_token, nonce=None):
        return validate_apple(id_token, nonce=nonce)


class GoogleAuthView(_BaseAuthView):
    def validator(self, id_token, nonce=None):
        return validate_google(id_token, nonce=nonce)
