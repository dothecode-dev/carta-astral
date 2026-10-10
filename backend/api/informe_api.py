"""Las operaciones HTTP del informe sobre un sujeto: leerlo, pedirlo, seguir su
avance, leer sus secciones y ver su índice.

Vivían en `views.py` atadas a una carta. Salieron acá para que el natal y el
vínculo (parte 3 de la spec de Vínculo) compartan las mismas respuestas: cada
vista resuelve y autoriza su sujeto —la carta propia, el vínculo propio— y
delega. Los chequeos van en funciones aparte porque el orden importa y es el
de siempre: mantenimiento, validación del pedido y recién después buscar el
sujeto (un `lang` inválido sobre una carta ajena es 400, no 404).

`transformar`, donde aparece, se aplica a cada texto que se devuelve: el
vínculo lo usa para mostrar los alias en lugar de «Persona A» (RF22).
"""

from collections.abc import Callable

from rest_framework import status
from rest_framework.response import Response

from api import informe_service, interpretation_service, mantenimiento
from api.canje import SinDerecho
from api.exceptions import CapReached, GenerationInProgress
from api.interpretation_service import DISCLAIMERS
from api.models import Interpretation
from interpret.prompts import PROMPT_VERSION, TIER_CORTO, TIER_LARGO

LANGS = ("es", "en", "pt")
TIERS = (TIER_CORTO, TIER_LARGO)

Transformar = Callable[[str], str] | None


def _igual(texto: str) -> str:
    return texto


def validar_lang(params) -> Response | None:
    lang = params.get("lang", "es")
    if lang not in LANGS:
        return Response(
            {"error": f"lang debe ser uno de {LANGS}"}, status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def validar(params) -> Response | None:
    if (error := validar_lang(params)) is not None:
        return error
    if params.get("tier") not in TIERS:
        return Response(
            {"error": f"tier debe ser uno de {TIERS}"}, status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def chequear_pedido(data) -> Response | None:
    """Antes de cobrar nada: un deploy en curso mataría el hilo a mitad de
    camino y dejaría el informe a medias con el derecho gastado. 503 y no 409
    porque es exactamente eso —el servicio no está disponible ahora— y la web
    ya lo traduce a "probá en un rato"."""
    if mantenimiento.activo():
        return Response(
            {"error": "estamos actualizando el sitio, probá en unos minutos"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return validar(data)


def leer(sujeto, params, transformar: Transformar = None) -> Response:
    """La lectura ya escrita, si existe. No genera ni cobra nada."""
    t = transformar or _igual
    lang, tier = params.get("lang", "es"), params.get("tier")
    # Filtrado por tier (RF9, RF20): con dos productos pudiendo convivir
    # en el mismo (sujeto, lang), sin este filtro cuál de los dos sirve
    # `.first()` queda a criterio del motor — entregar el informe
    # completo a quien pidió la breve (o al revés) es entregar el
    # producto equivocado.
    interp = sujeto.interpretations.filter(
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
    cuerpo = {
        "text": t(interp.text),
        "lang": interp.lang,
        "prompt_version": interp.prompt_version,
        "disclaimer": DISCLAIMERS[interp.lang],
        "created_at": interp.created_at.isoformat(),
    }
    if tier == TIER_LARGO:
        # Para el índice (spec 2026-10-07 RF8): las secciones con su título
        # del catálogo. `text` se queda para el PDF y la app.
        cuerpo["secciones"] = _con(informe_service.secciones_escritas(interp), t)
    return Response(cuerpo)


def pedir(sujeto, data, account) -> Response:
    """Arranca la generación pedida (la lectura breve o el informe de
    ocho secciones, según `tier`) y devuelve el control enseguida
    (RF10): cuatro minutos dentro de la vista bloquean uno de los tres
    workers sync de gunicorn, y tres pedidos a la vez dejan el sitio sin
    atender. Cobrar y crear la fila pendiente sigue siendo sincrónico —así
    un 402/503 por falta de crédito o cap alcanzado se responde antes de
    aceptar el 202— pero generar las secciones corre en un hilo aparte; la
    web sigue el avance con `GET …/estado`."""
    lang, tier = data.get("lang", "es"), data.get("tier")
    try:
        interpretacion = interpretation_service.iniciar_generacion(
            sujeto, lang, account, tier=tier
        )
    except SinDerecho as exc:
        # `.capacidad` dice cuál faltó ("leer_breve", "leer_informe" o
        # "leer_vinculo"): la web muestra pantallas distintas ("te quedaste
        # sin lecturas gratis" no es lo mismo que "comprá el informe
        # completo").
        return Response(
            {"error": "sin créditos disponibles", "code": f"sin_{exc.capacidad}"},
            status=status.HTTP_402_PAYMENT_REQUIRED,
        )
    except CapReached:
        # Con `code`, igual que el 402: sin él la web no puede distinguir
        # esto de una caída del servicio y mostraba "no pudimos generar la
        # lectura", que le dice a la persona que algo se rompió cuando lo
        # que pasó es que el cupo del día se acabó.
        return Response(
            {
                "error": "límite diario de informes alcanzado, probá más tarde",
                "code": "cap_diario",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except GenerationInProgress:
        # Ya hay una generación en curso para este sujeto en otro idioma
        # (BUG de la revisión de seguridad: cobrar acá y esperar dejaba
        # un crédito cobrado sin generación posible). 409: la web ya lo
        # traduce a "generación en curso" y reintenta más tarde.
        return Response(
            {"error": "generación en curso para esta carta en otro idioma"},
            status=status.HTTP_409_CONFLICT,
        )
    except ValueError:
        # Un tier que este producto no tiene (el vínculo no tiene lectura
        # breve): `capacidad()` lo rechaza antes de crear ni cobrar nada.
        return Response(
            {"error": "tier inválido para este producto"}, status=status.HTTP_400_BAD_REQUEST,
        )

    # El hilo lo lanza el servicio: el webhook arranca informes por el mismo
    # camino, y el patrón —cerrar la conexión, no morir en silencio— tiene
    # que estar escrito una sola vez.
    interpretation_service.arrancar_en_hilo(interpretacion, account)
    return Response(status=status.HTTP_202_ACCEPTED)


def estado(sujeto, params) -> Response:
    """Cuántas secciones ya están escritas: lo que la web sondea mientras
    `pedir` genera en segundo plano."""
    lang, tier = params.get("lang", "es"), params.get("tier")
    # Filtrado por tier, mismo motivo que en `leer`: sin él, con dos
    # productos conviviendo en (sujeto, lang), `.first()` podía devolver el
    # progreso del informe completo a quien sondea la lectura breve.
    interpretacion = Interpretation.objects.filter(
        sujeto=sujeto, lang=lang, prompt_version=PROMPT_VERSION, tier=tier,
    ).first()
    total = len(informe_service.secciones_aplicables(sujeto, tier))
    if interpretacion is None:
        return Response({"completa": False, "hechas": 0, "total": total})
    return Response(
        {
            "completa": interpretacion.completa,
            "hechas": interpretacion.secciones.count(),
            "total": total,
        }
    )


def secciones(sujeto, params, transformar: Transformar = None) -> Response:
    """Las secciones ya escritas, con texto: seis minutos de lectura en vez
    de seis minutos mirando una animación."""
    t = transformar or _igual
    lang, tier = params.get("lang", "es"), params.get("tier")
    total = len(informe_service.secciones_aplicables(sujeto, tier))
    # `select_related`: `secciones_escritas` vuelve a leer el sujeto y su carta.
    interpretacion = Interpretation.objects.select_related("sujeto__natal_de").filter(
        sujeto=sujeto, lang=lang, prompt_version=PROMPT_VERSION, tier=tier,
    ).first()
    if interpretacion is None:
        return Response(
            {"completa": False, "total": total, "secciones": [], "disclaimer": DISCLAIMERS[lang]}
        )
    return Response({
        "completa": interpretacion.completa,
        "total": total,
        "secciones": _con(informe_service.secciones_escritas(interpretacion), t),
        # El aviso lo agrega el sistema, no el modelo (los prompts le piden
        # que no lo escriba): quien lee mientras se escribe lo ve igual que
        # en la lectura terminada.
        "disclaimer": DISCLAIMERS[lang],
    })


def indice(sujeto, params, transformar: Transformar = None) -> Response:
    """El índice del informe completo (RF3): títulos de sus secciones y, si
    ya hay algo generado, el arranque de cada una. Se puede pedir sin haber
    comprado — es justamente lo que decide la compra."""
    t = transformar or _igual
    return Response([
        {**item, "parrafo": t(item["parrafo"])}
        for item in informe_service.indice_informe(sujeto, params.get("lang", "es"))
    ])


def _con(secciones_: list[dict], t: Callable[[str], str]) -> list[dict]:
    return [{**s, "texto": t(s["texto"])} for s in secciones_]
