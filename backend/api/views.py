import logging

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
    create_session,
)
from api.deletion import delete_account, delete_charts
from api.chart_service import create_chart
from api.interpretation_service import (
    DISCLAIMERS,
    CapReached,
    GenerationInProgress,
    QuotaExceeded,
    get_or_create_interpretation,
)
from interpret.prompts import PROMPT_VERSION
from api import apple
from api.ledger import credits_available as account_credits_available
from api.models import Chart, ProviderIdentity
from api.permissions import HasAccount
from api.sso import SSONotConfigured, SSOError, validate_apple, validate_google

logger = logging.getLogger(__name__)

_INTERPRETATION_LANGS = ("es", "en", "pt")


class AccountView(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request):
        return Response({
            "credits_available": account_credits_available(request.user),
            "account_id": request.user.id,
        })

    def delete(self, request):
        delete_account(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _chart_repr(chart: Chart) -> dict:
    birth = chart.birth_data
    # Con prefetch_related("interpretations") esto no agrega queries por carta.
    langs = sorted(
        {i.lang for i in chart.interpretations.all() if i.prompt_version == PROMPT_VERSION}
    )
    return {
        "id": str(chart.uuid),
        "house_system": chart.house_system,
        "zodiac": chart.zodiac,
        "data": chart.data,
        "engine_version": chart.engine_version,
        "interpretation_langs": langs,
        "birth": {
            "name": birth.name,
            "date": birth.date.isoformat(),
            "time": birth.time.strftime("%H:%M") if birth.time else None,
            "time_known": birth.time_known,
            "lat": birth.lat,
            "lng": birth.lng,
            "tz_name": birth.tz_name,
            "place_label": birth.place_label,
        },
    }


class ChartCollectionView(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]
    throttle_scope = "chart"

    def get_throttles(self):
        # El throttle de creación (scope "chart") aplica SÓLO al POST: crear una
        # carta calcula efemérides (CPU). El GET de listado no gasta ese cupo.
        if self.request.method == "POST":
            return [ScopedRateThrottle()]
        return []

    def get(self, request):
        charts = (
            Chart.objects.filter(account=request.user)
            .select_related("birth_data")
            .prefetch_related("interpretations")
            .order_by("-created_at")
        )
        return Response({"results": [_chart_repr(c) for c in charts]})

    def post(self, request):
        try:
            chart = create_chart(request.data, request.user)
        except (KeyError, ValueError, CoreError) as exc:
            logger.warning("chart creation rejected: %s", exc, exc_info=True)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_chart_repr(chart), status=status.HTTP_201_CREATED)

    def delete(self, request):
        delete_charts(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChartDetailView(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request, uuid):
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)
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

    def get(self, request, uuid):
        """La lectura ya escrita, si existe. No genera ni cobra nada."""
        lang = request.query_params.get("lang", "es")
        if lang not in _INTERPRETATION_LANGS:
            return Response(
                {"error": f"lang debe ser uno de {_INTERPRETATION_LANGS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)
        interp = chart.interpretations.filter(
            lang=lang, prompt_version=PROMPT_VERSION
        ).first()
        if interp is None:
            # Incluye el caso de una lectura escrita con un prompt viejo: ya no
            # es la que el sistema generaría hoy.
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "text": interp.text,
                "lang": interp.lang,
                "prompt_version": interp.prompt_version,
                "disclaimer": DISCLAIMERS[interp.lang],
                "created_at": interp.created_at.isoformat(),
            }
        )

    def post(self, request, uuid):
        lang = request.data.get("lang", "es")
        if lang not in _INTERPRETATION_LANGS:
            return Response(
                {"error": f"lang debe ser uno de {_INTERPRETATION_LANGS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)
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
        except GenerationInProgress:
            # No es una falla: hay otra petición escribiendo esta misma lectura.
            # 409 para que el cliente espere y la pida, en vez de mostrar error.
            return Response(
                {"error": "generación en curso"},
                status=status.HTTP_409_CONFLICT,
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
        self.after_login(request, vid)
        token = create_session(account)
        return Response({
            "token": token,
            "credits_available": account_credits_available(account),
            "account_id": account.id,
        })

    def after_login(self, request, vid):
        """Hook post-resolución de cuenta. Por defecto no hace nada."""


class AppleAuthView(_BaseAuthView):
    def validator(self, id_token, nonce=None):
        return validate_apple(id_token, nonce=nonce)

    def after_login(self, request, vid):
        """Canjea el authorization_code por el refresh_token que pide el revoke.

        Best-effort: si Apple falla, el usuario entra igual. Un login roto es
        peor que un revoke que después no se puede hacer (queda logueado).
        """
        code = request.data.get("authorization_code")
        if not code or not apple.is_configured():
            return
        try:
            refresh_token = apple.exchange_code(code)
        except Exception as exc:  # AppleError / AppleNotConfigured
            logger.warning("apple: canje de authorization_code falló: %s", exc)
            return
        ProviderIdentity.objects.filter(provider="apple", sub=vid.sub).update(
            refresh_token=refresh_token
        )


class GoogleAuthView(_BaseAuthView):
    def validator(self, id_token, nonce=None):
        return validate_google(id_token, nonce=nonce)
