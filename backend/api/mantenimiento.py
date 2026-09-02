"""Modo mantenimiento: dejar de aceptar trabajo antes de un deploy.

Un deploy mata el contenedor viejo con su hilo adentro, y con él el informe que
estuviera escribiendo. `reanudar_informes` lo rescata en la corrida siguiente,
pero quien pagó espera de más. La salida es no arrancar nada nuevo y esperar a
que termine lo que hay: eso es lo que hace `make deploy` antes de pushear.

El flag vive en la caché, que en producción es la base (`USE_DB_CACHE`, y el
settings falla si no está): así sobrevive al deploy y lo ven los dos
contenedores que conviven durante el swap. Una variable de entorno no serviría
—cambiarla en Coolify dispara justamente el deploy que queremos ordenar— y un
archivo tampoco: el contenedor nuevo no lo vería.

Sin fecha de vencimiento: un mantenimiento que se apaga solo a los cinco
minutos, en medio de un deploy que tardó más, es peor que uno que se queda
prendido — al menos ése se ve. `make deploy` lo apaga con `trap`, incluso si el
deploy falla o alguien corta con Ctrl-C.
"""

from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api import interpretation_service
from api.models import Interpretation
from interpret.prompts import PROMPT_VERSION

CLAVE = "astra:mantenimiento"


def activo() -> bool:
    """Si el sitio está cerrado para trabajo nuevo.

    Ante la duda, ABIERTO: si la caché se vacía o el flag falta, el sitio sigue
    funcionando. Fallar al revés dejaría el cartel puesto sin que nadie lo haya
    pedido, y sin forma de darse cuenta salvo entrando.
    """
    return cache.get(CLAVE) is not None


def activar() -> None:
    cache.set(CLAVE, "1", None)


def desactivar() -> None:
    cache.delete(CLAVE)


def generando() -> int:
    """Cuántos informes se están escribiendo AHORA, que es lo que un deploy
    cortaría por la mitad.

    Cuenta locks vivos, no filas incompletas: una fila sin lock ya está caída
    —el proceso murió— y a ésa la retoma el cron, así que esperarla sería
    esperar para siempre. Mismo criterio que `esta_generandose`.
    """
    pendientes = Interpretation.objects.filter(
        completa=False, prompt_version=PROMPT_VERSION,
    ).select_related("chart")
    return sum(
        1 for i in pendientes
        if i.chart is not None and interpretation_service.esta_generandose(i.chart, i.tier)
    )


class EstadoView(APIView):
    """`GET /api/estado/` — si el sitio acepta trabajo, y cuánto queda en vuelo.

    Público y sin sesión a propósito: lo consulta `make deploy` desde afuera
    para saber cuándo puede pushear, y la web en cada request para decidir si
    muestra el cartel. No dice nada de nadie —dos números— así que no hay qué
    proteger.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"mantenimiento": activo(), "generando": generando()})
