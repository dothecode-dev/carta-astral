import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.exceptions import CoreError

from api import geocode, informe_api, interpretation_service
from api.accounts import resolve_account
from api.auth import (
    AccountTokenAuthentication,
    create_session,
)
from api.deletion import delete_account, delete_charts
from api import chart_service
from api.chart_service import CartaCalculada, calcular, create_chart, mensaje_de_datos_invalidos
from api.canje import derechos_de
from api.firma_frases import firma
from interpret.prompts import PROMPT_VERSION
from api import apple
from api.models import Chart, ProviderIdentity, Sujeto
from api.permissions import HasAccount
from api.serializers import serialize_chart_data
from api.sujetos import sujeto_natal
from api.versioning import engine_version
from api.sso import SSONotConfigured, SSOError, validate_apple, validate_google

logger = logging.getLogger(__name__)

class AccountView(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request):
        return Response({
            # Con qué mail entraste. Puede venir vacío —Apple deja ocultarlo—,
            # pero el campo está siempre: la pantalla muestra lo que haya, y
            # sin esto no había forma de darse cuenta de que uno quedó
            # logueado con la cuenta equivocada.
            "email": request.user.email,
            "derechos": derechos_de(request.user),
            "deuda": request.user.deuda,
            "account_id": request.user.id,
        })

    def delete(self, request):
        try:
            delete_account(request.user)
        except ImproperlyConfigured as exc:
            # `sub_hash("email", ...)` exige TOMBSTONE_HMAC_KEY (I3, revisión
            # de `puertas-de-acceso`): antes de esta identidad ninguna cuenta
            # llegaba acá con provider="email", así que este camino no
            # existía. Es una configuración faltante, no un pedido mal
            # formado — 503, no el 500 pelado que tenía antes. Mismo
            # tratamiento que `CanjearCodigoView` en `api/sessions.py`.
            logger.error("borrado de cuenta no disponible: %s", exc)
            return Response(
                {"error": "borrado no disponible"}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


def _chart_repr(chart: Chart) -> dict:
    birth = chart.birth_data
    # Los informes cuelgan del sujeto natal (parte 2 de Vínculo). La relación
    # y no `sujeto_natal()`: con el prefetch del listado ya está cargada, y la
    # función haría una consulta por carta. Si faltara, se crea.
    try:
        sujeto = chart.sujeto_natal
    except Sujeto.DoesNotExist:
        sujeto = sujeto_natal(chart)
    informes = sujeto.interpretations.all()
    # Con prefetch_related("sujeto_natal__interpretations") esto no agrega queries por
    # carta (por eso no delega en `interpretation_service.interpretation_langs`,
    # que haría una consulta propia por carta). `completa` es la misma
    # condición que esa función aplica: una fila `completa=False` es la
    # generación en curso que crea `iniciar_generacion` (Tarea 10), no una
    # lectura disponible.
    langs = sorted(
        {
            i.lang for i in informes
            if i.prompt_version == PROMPT_VERSION and i.completa
        }
    )
    # Por idioma, qué informes están listos. `interpretation_langs` (un set de
    # idiomas) alcanzaba con un solo producto; con dos, la web necesita saber
    # si ofrecer el informe completo sobre una carta que ya tiene la breve, o
    # si ya tiene ambos y no ofrecer de nuevo la breve. Mismo criterio que
    # `langs` arriba (completa=True y prompt_version vigente) y misma pasada
    # sobre `informes`, ya resuelta por el
    # prefetch_related del listado: no agrega queries por carta.
    #
    # Sólo aparecen los idiomas con al menos un tier completo —`setdefault`
    # no crea la clave para un idioma sin nada listo—, no los tres idiomas
    # soportados con lista vacía. La web lo lee como
    # `interpretations[lang] ?? []`, así que el resultado es el mismo sin
    # cargar el payload de claves vacías por cada carta.
    tiers_por_lang: dict[str, list[str]] = {}
    for i in informes:
        if i.completa and i.prompt_version == PROMPT_VERSION:
            tiers_por_lang.setdefault(i.lang, []).append(i.tier)
    # `Interpretation` no tiene `Meta.ordering`: sin esto el orden depende del
    # plan de consulta de Postgres y no está garantizado entre corridas — a
    # diferencia de `langs` arriba, que ya fuerza orden con `sorted(...)`.
    for tiers in tiers_por_lang.values():
        tiers.sort()
    # Qué se va a terminar, por idioma. Sin esto, quien pide su informe,
    # cierra la pestaña y vuelve más tarde encuentra la carta ofreciéndole
    # generar de nuevo lo que ya pagó: `interpretations` sólo lista lo
    # terminado, así que "no tiene" y "se está generando" eran el mismo payload.
    #
    # Lo decidía `esta_generandose` (el lock vivo) porque el único que podía
    # retomar un intento caído era el usuario apretando el botón de nuevo. Con
    # `reanudar_informes` corriendo por cron eso dejó de ser cierto: un lock
    # vencido es una pausa —el cron lo retoma mientras queden intentos—, no un
    # final. Con el criterio viejo, un informe pago que se cortó volvía a
    # mostrar el bloque de venta de US$ 29; pasó en producción el 01-09-2026.
    #
    # El corte es `INTENTOS_MAXIMOS`, el mismo que usa el cron: agotados los
    # tres, RF21 devuelve el derecho y borra la fila, y ahí sí corresponde
    # volver a ofrecer la compra —con el derecho de nuevo en la cuenta—. Sin
    # ese corte, una fila que nadie va a terminar deja la pantalla esperando
    # para siempre.
    #
    # Va también en el listado, no sólo en el detalle: el propio contrato de la
    # API advierte que cuando listado y detalle divergen la app rompe al navegar
    # entre uno y otro (ya pasó con `interpretation_langs`).
    en_curso: dict[str, list[str]] = {}
    for i in informes:
        if i.completa or i.prompt_version != PROMPT_VERSION:
            continue
        if i.intentos >= interpretation_service.INTENTOS_MAXIMOS:
            continue
        en_curso.setdefault(i.lang, []).append(i.tier)
    for tiers in en_curso.values():
        tiers.sort()

    return {
        "id": str(chart.uuid),
        "house_system": chart.house_system,
        "zodiac": chart.zodiac,
        "data": chart.data,
        "firma": firma(chart.data),
        "engine_version": chart.engine_version,
        "interpretation_langs": langs,
        "interpretations": tiers_por_lang,
        "trato": birth.trato,
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
        "en_curso": en_curso,
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
            .select_related("birth_data", "sujeto_natal")
            .prefetch_related("sujeto_natal__interpretations")
            .order_by("-created_at")
        )
        return Response({"results": [_chart_repr(c) for c in charts]})

    def post(self, request):
        try:
            chart = create_chart(request.data, request.user)
        except (KeyError, ValueError, CoreError) as exc:
            # Sin `exc_info` ni el mensaje: el traceback adjunta las variables
            # locales, y acá adentro están los datos de nacimiento.
            logger.warning("chart creation rejected: %s", type(exc).__name__)
            return Response(
                {"error": mensaje_de_datos_invalidos(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(_chart_repr(chart), status=status.HTTP_201_CREATED)

    def delete(self, request):
        delete_charts(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _preview_repr(carta: CartaCalculada) -> dict:
    """La misma forma que `_chart_repr`, menos lo que sólo existe guardado.

    Sin `id`: no hay fila, y un identificador invitaría a la web a pedirle al
    backend algo que no está. `interpretations` y `en_curso` van vacíos —no
    ausentes— para que los componentes de la carta no tengan que distinguir
    este caso del de una carta propia recién creada.
    """
    bi = carta.birth_input
    data = serialize_chart_data(carta.data)
    return {
        "house_system": carta.data.house_system,
        "zodiac": carta.data.zodiac,
        "data": data,
        # Sol, Luna y Ascendente en palabras: lo único de la carta que entiende
        # quien no sabe leer glifos. Texto fijo, sin costo de modelo.
        "firma": firma(data),
        "engine_version": engine_version(),
        "interpretation_langs": [],
        "interpretations": {},
        "en_curso": {},
        "birth": {
            "name": bi.name,
            "date": bi.date.isoformat(),
            "time": bi.time.strftime("%H:%M") if bi.time else None,
            "time_known": carta.data.time_known,
            "lat": bi.lat,
            "lng": bi.lng,
            "tz_name": carta.tz_name,
            "place_label": carta.place_label,
        },
    }


class ChartPreviewView(APIView):
    """La carta de quien todavía no tiene cuenta.

    El CTA de la home mandaba a `/nueva`, que exigía entrar: el visitante frío
    chocaba con un login antes de ver nada, mientras `/precios` le prometía
    tres lecturas gratis. Acá ve SU rueda —no la carta de ejemplo, que es la
    de otra persona— y la cuenta se pide recién para la interpretación, que es
    lo que cuesta plata.

    Calcula y no guarda: la fecha, la hora y el lugar de nacimiento son dato
    sensible de alguien que todavía no aceptó nada. Si después entra, la web
    reenvía esos datos y ahí sí se crea la carta.

    El techo es por IP porque no hay cuenta a la que atribuir el gasto. No
    cubre el costo del LLM —el preview no lo usa— sino la CPU de las
    efemérides, que es lo único que se puede quemar desde acá.
    """

    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "preview"

    def post(self, request):
        try:
            carta = calcular(request.data)
        except (KeyError, ValueError, CoreError) as exc:
            # Sin `exc_info` y sin el payload: el traceback de Sentry adjunta
            # las variables locales del marco, y acá adentro está la fecha de
            # nacimiento de una persona que ni siquiera tiene cuenta.
            logger.warning("preview rechazado: %s", type(exc).__name__)
            return Response(
                {"error": mensaje_de_datos_invalidos(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(_preview_repr(carta))


class ChartDetailView(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request, uuid):
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)
        return Response(_chart_repr(chart))

    def patch(self, request, uuid):
        chart = get_object_or_404(
            Chart.objects.select_related("birth_data", "sujeto_natal").prefetch_related("sujeto_natal__interpretations"),
            uuid=uuid, account=request.user,
        )
        try:
            chart_service.cambiar_trato(chart, request.data)
        except chart_service.TratoInvalido:
            return Response({"error": "trato inválido"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_chart_repr(chart))


class GeocodeView(APIView):
    # Abierta desde el 04-09-2026: el formulario de `/nueva` funciona sin
    # cuenta, y sin esto el visitante no podía ni decir dónde nació (heredaba
    # `HasAccount` del default de DRF por no declarar permiso propio).
    # El techo es por IP y generoso: el campo autocompleta mientras se
    # escribe, así que completar un formulario son varias consultas.
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geocode"

    def post(self, request):
        q = request.data.get("q", "")
        try:
            results = geocode.search(q)
        except ValueError as exc:
            logger.warning("geocode query rejected: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"results": results})


class InterpretationView(APIView):
    """El informe de una carta propia: leerlo (GET) y pedirlo (POST). La
    lógica vive en `informe_api`, compartida con el vínculo."""

    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "interpretation"

    def get(self, request, uuid):
        if (error := informe_api.validar(request.query_params)) is not None:
            return error
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)
        return informe_api.leer(sujeto_natal(chart), request.query_params)

    def post(self, request, uuid):
        if (error := informe_api.chequear_pedido(request.data)) is not None:
            return error
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)
        return informe_api.pedir(sujeto_natal(chart), request.data, request.user)


class InterpretationEstadoView(APIView):
    """Cuántas secciones del informe ya están escritas. Sin throttle de
    "interpretation": se consulta muchas veces durante los ~4 minutos que
    tarda un informe."""

    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request, uuid):
        if (error := informe_api.validar(request.query_params)) is not None:
            return error
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)
        return informe_api.estado(sujeto_natal(chart), request.query_params)


class InterpretationSeccionesView(APIView):
    """Las secciones ya escritas del informe, con texto. Misma validación
    que `estado`."""

    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request, uuid):
        if (error := informe_api.validar(request.query_params)) is not None:
            return error
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)
        return informe_api.secciones(sujeto_natal(chart), request.query_params)


class IndiceInformeView(APIView):
    """El índice del informe completo (RF3). No exige créditos ni dispara
    generación."""

    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request, uuid):
        if (error := informe_api.validar_lang(request.query_params)) is not None:
            return error
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)
        return informe_api.indice(sujeto_natal(chart), request.query_params)


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
            "derechos": derechos_de(account),
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
