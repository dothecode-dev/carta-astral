import logging
import threading

from django.conf import settings
from django.db import connections
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.exceptions import CoreError

from api import geocode, informe_service, interpretation_service
from api.accounts import resolve_account
from api.auth import (
    AccountTokenAuthentication,
    create_session,
)
from api.deletion import delete_account, delete_charts
from api.chart_service import create_chart
from api.exceptions import CapReached, GenerationInProgress, QuotaExceeded
from api.interpretation_service import DISCLAIMERS
from interpret.prompts import PROMPT_VERSION, TIER_CORTO, TIER_LARGO
from api import apple
from api.ledger import credits_available as account_credits_available
from api.models import Chart, Interpretation, ProviderIdentity
from api.permissions import HasAccount
from api.sso import SSONotConfigured, SSOError, validate_apple, validate_google

logger = logging.getLogger(__name__)

_INTERPRETATION_LANGS = ("es", "en", "pt")
# Sin default a propósito (RF9, RF20): adivinar el tier es gastar el lote de
# crédito equivocado (free para la breve, paid para el informe completo), y
# un default silencioso convertiría un olvido del cliente en un cobro de
# US$ 29 sin que nadie lo haya pedido.
_TIERS = (TIER_CORTO, TIER_LARGO)


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
    # Con prefetch_related("interpretations") esto no agrega queries por
    # carta (por eso no delega en `interpretation_service.interpretation_langs`,
    # que haría una consulta propia por carta). `completa` es la misma
    # condición que esa función aplica: una fila `completa=False` es la
    # generación en curso que crea `iniciar_generacion` (Tarea 10), no una
    # lectura disponible.
    langs = sorted(
        {
            i.lang for i in chart.interpretations.all()
            if i.prompt_version == PROMPT_VERSION and i.completa
        }
    )
    # Por idioma, qué informes están listos. `interpretation_langs` (un set de
    # idiomas) alcanzaba con un solo producto; con dos, la web necesita saber
    # si ofrecer el informe completo sobre una carta que ya tiene la breve, o
    # si ya tiene ambos y no ofrecer de nuevo la breve. Mismo criterio que
    # `langs` arriba (completa=True y prompt_version vigente) y misma pasada
    # sobre `chart.interpretations.all()`, ya resuelta por el
    # prefetch_related del listado: no agrega queries por carta.
    tiers_por_lang: dict[str, list[str]] = {}
    for i in chart.interpretations.all():
        if i.completa and i.prompt_version == PROMPT_VERSION:
            tiers_por_lang.setdefault(i.lang, []).append(i.tier)
    return {
        "id": str(chart.uuid),
        "house_system": chart.house_system,
        "zodiac": chart.zodiac,
        "data": chart.data,
        "engine_version": chart.engine_version,
        "interpretation_langs": langs,
        "interpretations": tiers_por_lang,
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
        tier = request.query_params.get("tier")
        if tier not in _TIERS:
            return Response(
                {"error": f"tier debe ser uno de {_TIERS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)
        # Filtrado por tier (RF9, RF20): con dos productos pudiendo convivir
        # en el mismo (chart, lang), sin este filtro cuál de los dos sirve
        # `.first()` queda a criterio del motor — entregar el informe
        # completo a quien pidió la breve (o al revés) es entregar el
        # producto equivocado.
        interp = chart.interpretations.filter(
            lang=lang, prompt_version=PROMPT_VERSION, tier=tier,
        ).first()
        if interp is None or not interp.completa:
            # Incluye el caso de una lectura escrita con un prompt viejo (ya no
            # es la que el sistema generaría hoy) y el de la Tarea 10: apenas
            # arranca el hilo de fondo, `iniciar_generacion` ya creó la fila
            # (completa=False, text=""). Antes de este chequeo eso devolvía
            # 200 con text="": un "éxito" que la web no podía distinguir de
            # una lectura vacía de verdad, y la dejaba en una pantalla en
            # blanco sin botón de reintento. 404 —el mismo código que "no
            # existe todavía"— es un estado que el cliente puede manejar
            # (reintentar, o consultar `/estado` para seguir el progreso);
            # un 200 vacío no.
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
        """Arranca la generación pedida (la lectura breve o el informe de
        ocho secciones, según `tier`) y devuelve el control enseguida
        (RF10): cuatro minutos dentro de esta vista bloquean uno de los tres
        workers sync de gunicorn, y tres pedidos a la vez dejan el sitio sin
        atender. Cobrar y crear la fila pendiente sigue siendo sincrónico —así
        un 402/503 por falta de crédito o cap alcanzado se responde antes de
        aceptar el 202— pero generar las secciones corre en un hilo aparte; la
        web sigue el avance con `GET .../interpretation/estado`."""
        lang = request.data.get("lang", "es")
        if lang not in _INTERPRETATION_LANGS:
            return Response(
                {"error": f"lang debe ser uno de {_INTERPRETATION_LANGS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tier = request.data.get("tier")
        if tier not in _TIERS:
            return Response(
                {"error": f"tier debe ser uno de {_TIERS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)
        account = request.user
        try:
            interpretacion = interpretation_service.iniciar_generacion(
                chart, lang, account, tier=tier
            )
        except QuotaExceeded as exc:
            # `.lote` dice cuál crédito faltó ("free" o "paid"): la web
            # muestra dos pantallas distintas ("te quedaste sin lecturas
            # gratis" no es lo mismo que "comprá el informe completo").
            return Response(
                {"error": "sin créditos disponibles", "code": f"sin_{exc.lote}"},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        except CapReached:
            return Response(
                {"error": "límite diario de informes alcanzado, probá más tarde"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except GenerationInProgress:
            # Ya hay una generación en curso para esta carta en otro idioma
            # (BUG de la revisión de seguridad: cobrar acá y esperar dejaba
            # un crédito cobrado sin generación posible). 409: la web ya lo
            # traduce a "generación en curso" y reintenta más tarde, igual
            # que hacía con el 409 síncrono que existía antes de la Task 10.
            return Response(
                {"error": "generación en curso para esta carta en otro idioma"},
                status=status.HTTP_409_CONFLICT,
            )

        def _en_hilo():
            # Un hilo nuevo no hereda la conexión a la base del request: cada
            # consulta abre la suya propia (thread-local), y hay que cerrarla
            # explícitamente al terminar o la conexión queda pérdida (mismo
            # patrón que `tests/api/test_ledger_concurrencia.py`). El
            # try/except de acá afuera es la red de seguridad final: si algo
            # revienta dentro de `completar_generacion` que ni su propio
            # try/except contempla, esto lo loguea igual — un hilo de fondo
            # que muere en silencio deja el informe colgado y nadie se entera.
            try:
                interpretation_service.completar_generacion(interpretacion, chart, account)
            except Exception:
                logger.exception(
                    "el hilo de generación del informe %s murió sin control",
                    interpretacion.pk,
                )
            finally:
                connections.close_all()

        threading.Thread(target=_en_hilo, daemon=True).start()
        return Response(status=status.HTTP_202_ACCEPTED)


class InterpretationEstadoView(APIView):
    """Cuántas secciones del informe ya están escritas. Es lo que la web
    sondea mientras `InterpretationView.post` genera en segundo plano
    (RF7/RF10): sin throttle de "interpretation" porque se consulta muchas
    veces durante los ~4 minutos que tarda un informe."""

    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request, uuid):
        lang = request.query_params.get("lang", "es")
        tier = request.query_params.get("tier")
        if tier not in _TIERS:
            return Response(
                {"error": f"tier debe ser uno de {_TIERS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)
        # Filtrado por tier, mismo motivo que en `InterpretationView.get`:
        # sin él, con dos productos conviviendo en (chart, lang), `.first()`
        # podía devolver el progreso del informe completo a quien está
        # sondeando la lectura breve (o al revés).
        interpretacion = Interpretation.objects.filter(
            chart=chart, lang=lang, prompt_version=PROMPT_VERSION, tier=tier,
        ).first()
        total = len(informe_service.secciones_aplicables(chart, tier))
        if interpretacion is None:
            return Response({"completa": False, "hechas": 0, "total": total})
        return Response(
            {
                "completa": interpretacion.completa,
                "hechas": interpretacion.secciones.count(),
                "total": total,
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
    def post(self, request):
        # Sign in with Apple existe sólo para la app: la web entra con Google
        # (`GoogleSignIn.tsx` es su único componente de login). Mientras no haya
        # app, la ruta no se anuncia. 404 y no 503 porque acá nadie reintenta.
        if not settings.APP_AUTH_ENABLED:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return super().post(request)

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
