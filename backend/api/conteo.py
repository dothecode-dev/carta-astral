"""Conteo propio por día, sin cookies ni datos personales (`ConteoDiario`).

Es el denominador real del embudo: PostHog sólo ve a quien acepta las
cookies. Contar nunca puede romper lo que cuenta: si la base falla, se loguea
y se sigue, y el fallo queda en su propio savepoint para no envenenar la
transacción de quien llamó.
"""

import datetime
import logging
import zoneinfo
from functools import cache
from urllib.parse import urlsplit

from django.db import DatabaseError, transaction
from django.db.models import F
from django.utils import timezone

from api.models import ConteoDiario, ConteoProcedencia, PasarelaCheckout

logger = logging.getLogger(__name__)

EVENTOS = tuple(clave for clave, _ in ConteoDiario.EVENTOS)
EVENTOS_TEASER = tuple(e for e in EVENTOS if e.startswith("teaser_"))

# Lo que el navegador puede pedir que se cuente, y nada más: no puede inventar
# contadores ni sumarle a los que cuenta el servidor solo (`carta_calculada`).
# Sale de `ConteoDiario.EVENTOS`, la única lista: un paso nuevo es una línea
# ahí (y su migración). `teaser_clic_<moneda>` no es un paso: lo suma un clic.
_POSICIONES_CLIC = ("clic_arriba", "clic_cierre")
_SIN_PREFIJO = tuple(e.removeprefix("teaser_") for e in EVENTOS_TEASER)
MONEDAS_CLIC = tuple(
    p.removeprefix("clic_") for p in _SIN_PREFIJO if p.startswith("clic_") and p not in _POSICIONES_CLIC
)
PASOS_TEASER = tuple(p for p in _SIN_PREFIJO if not p.startswith("clic_") or p in _POSICIONES_CLIC)


def contar(evento: str) -> None:
    """Suma uno al contador de hoy (UTC) para `evento`."""
    if evento not in EVENTOS:
        logger.error("conteo: evento desconocido %r", evento)
        return
    try:
        with transaction.atomic():
            _incrementar(ConteoDiario, fecha=timezone.now().date(), evento=evento)
    except DatabaseError:
        logger.exception("conteo: no se pudo contar %s", evento)


def contar_teaser(paso: object, moneda: object = None) -> bool:
    """Un paso del teaser sin cuenta. Un clic en comprar cuenta además en qué
    moneda se mostró el precio. Devuelve False, sin contar nada, si `paso` o
    `moneda` no son de las listas cerradas."""
    if not isinstance(paso, str) or paso not in PASOS_TEASER:
        return False
    if moneda is not None and (not isinstance(moneda, str) or moneda not in MONEDAS_CLIC):
        return False
    contar(f"teaser_{paso}")
    if moneda and paso.startswith("clic_"):
        contar(f"teaser_clic_{moneda}")
    return True


def _incrementar(modelo, **clave) -> None:
    """Suma uno a la fila de `clave`, creándola si es la primera del día.

    Lo común es que ya exista: un solo UPDATE (cantidad = cantidad + 1,
    atómico entre procesos). Si dos la crean a la vez, `get_or_create`
    resuelve el choque y el UPDATE de abajo suma igual. Lo llama quien abre
    el savepoint y atrapa el error.
    """
    if not modelo.objects.filter(**clave).update(cantidad=F("cantidad") + 1):
        fila, _ = modelo.objects.get_or_create(**clave)
        modelo.objects.filter(pk=fila.pk).update(cantidad=F("cantidad") + 1)


def resumen(dias: int = 7) -> dict:
    """Los últimos `dias` días COMPLETOS (UTC), por día y en total, y hoy aparte.

    Hoy va separado porque el informe sale a la mañana: con unas horas, sumarlo
    o ponerlo en fila con días enteros se lee como una caída.

    `compra_pagada` sale de los pagos acreditados (`PasarelaCheckout`), no de
    un contador: ya está en la base. No cuentan los canjes con cupón del 100 %
    ni las compras reembolsadas. Los contadores cuentan VECES, no personas.
    """
    hoy = timezone.now().date()
    fechas = [hoy - datetime.timedelta(days=i) for i in range(1, dias + 1)]
    claves = (*EVENTOS, "compra_pagada")
    por_dia = {str(f): dict.fromkeys(claves, 0) for f in (hoy, *fechas)}
    for fila in ConteoDiario.objects.filter(fecha__gte=fechas[-1]):
        por_dia[str(fila.fecha)][fila.evento] = fila.cantidad
    pagas = PasarelaCheckout.objects.filter(
        acreditado_at__date__gte=fechas[-1], reembolsado_centavos=0,
    ).exclude(checkout_id__startswith="cupon_")
    for acreditado in pagas.values_list("acreditado_at", flat=True):
        dia = str(acreditado.date())
        if dia in por_dia:
            por_dia[dia]["compra_pagada"] += 1
    hoy_parcial = por_dia.pop(str(hoy))
    total = {c: sum(d[c] for d in por_dia.values()) for c in claves}
    return {"dias": dias, "total": total, "hoy": hoy_parcial, "por_dia": por_dia}


def serie(dias: int = 90) -> dict:
    """La historia diaria para el gráfico, del día más viejo a hoy (incluido).

    Una lista por evento, alineada con `fechas`, con 0 donde no hubo nada.
    `compra_pagada` con el mismo criterio que `resumen`.
    """
    hoy = timezone.now().date()
    fechas = [hoy - datetime.timedelta(days=i) for i in range(dias - 1, -1, -1)]
    indice = {f: i for i, f in enumerate(fechas)}
    claves = (*EVENTOS, "compra_pagada")
    valores = {c: [0] * dias for c in claves}
    for fila in ConteoDiario.objects.filter(fecha__gte=fechas[0]):
        valores[fila.evento][indice[fila.fecha]] = fila.cantidad
    pagas = PasarelaCheckout.objects.filter(
        acreditado_at__date__gte=fechas[0], reembolsado_centavos=0,
    ).exclude(checkout_id__startswith="cupon_")
    for acreditado in pagas.values_list("acreditado_at", flat=True):
        if (i := indice.get(acreditado.date())) is not None:
            valores["compra_pagada"][i] += 1
    return {"fechas": [str(f) for f in fechas], **valores}


# --- Procedencia --------------------------------------------------------------

CANALES = (
    "google_ads", "google", "otros_buscadores", "redes", "email", "otro_sitio", "otra_campana", "directo",
)
_BUSCADORES = ("bing.com", "duckduckgo.com", "search.yahoo.com", "yandex.com", "yandex.ru",
               "ecosia.org", "search.brave.com")
_REDES = ("facebook.com", "instagram.com", "t.co", "twitter.com", "x.com", "tiktok.com",
          "linkedin.com", "reddit.com", "whatsapp.com", "pinterest.com", "youtube.com", "threads.net")
_CORREO = ("mail.google.com", "com.google.android.gm", "outlook.live.com", "outlook.office.com",
           "mail.yahoo.com", "mail.proton.me")
# Volver de pagar o de entrar con Google o Apple no dice cómo llegó la persona.
_VUELTAS = ("checkout.stripe.com", "accounts.google.com", "appleid.apple.com")
_APP_GOOGLE = "com.google.android.googlequicksearchbox"
# Nombres con tilde que la base de zonas escribe sin ella.
_CON_TILDE = {"Bogota": "Bogotá", "Sao_Paulo": "São Paulo", "Asuncion": "Asunción", "Merida": "Mérida"}


def _es(host: str, dominios: tuple[str, ...]) -> bool:
    """Dominio completo o subdominio: «blogspot.com» no es «t.co»."""
    return any(host == d or host.endswith("." + d) for d in dominios)


def _es_buscador_google(host: str) -> bool:
    # google.com, www.google.com.ar, google.es…; no mail. ni accounts.
    return host == _APP_GOOGLE or host.startswith(("google.", "www.google."))


def canal_de(utm_source: object, referrer: object, gclid: object = False) -> str:
    """El canal, de `CANALES`, a partir de la dirección del anuncio y la página previa.

    Google Ads marca sus clics con `gclid` (auto-etiquetado) aunque no haya
    `utm_source`; la web sólo manda si estaba, nunca el valor.
    """
    utm = utm_source.strip().lower() if isinstance(utm_source, str) else ""
    if gclid is True or utm in ("google", "google_ads", "adwords"):
        return "google_ads"
    if utm:
        return "otra_campana"
    try:
        host = (urlsplit(referrer).hostname or "") if isinstance(referrer, str) else ""
    except ValueError:  # una URL mal formada («http://[») no es un canal
        return "otro_sitio"
    if not host or _es(host, _VUELTAS):
        return "directo"
    if _es(host, _CORREO):
        return "email"
    if _es_buscador_google(host):
        return "google"
    if _es(host, _BUSCADORES):
        return "otros_buscadores"
    if _es(host, _REDES):
        return "redes"
    return "otro_sitio"


@cache
def _zonas() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


def lugar_de_zona(zona: object) -> str:
    """La ciudad de referencia de una zona horaria real; las de Argentina, juntas."""
    if not isinstance(zona, str) or zona not in _zonas() or "/" not in zona:
        return "desconocida"
    if zona.startswith("America/Argentina/") or zona == "America/Buenos_Aires":
        return "Argentina"
    ciudad = zona.rsplit("/", 1)[1]
    return _CON_TILDE.get(ciudad, ciudad.replace("_", " "))


def contar_procedencia(procedencia: object) -> None:
    """Suma uno al canal y al lugar de quien calculó una carta. Nunca rompe."""
    datos = procedencia if isinstance(procedencia, dict) else {}
    canal = canal_de(datos.get("utm_source"), datos.get("referrer"), datos.get("gclid"))
    lugar = lugar_de_zona(datos.get("zona"))
    hoy = timezone.now().date()
    try:
        with transaction.atomic():
            _incrementar(ConteoProcedencia, fecha=hoy, tipo="canal", valor=canal)
            _incrementar(ConteoProcedencia, fecha=hoy, tipo="lugar", valor=lugar)
    except DatabaseError:
        logger.exception("conteo: no se pudo contar la procedencia")


def serie_procedencia(tipo: str, dias: int = 90, top: int = 5) -> dict:
    """La historia diaria de los `top` valores más frecuentes del período, y el
    resto sumado en «otros»: así las series suman lo mismo que las cartas."""
    hoy = timezone.now().date()
    fechas = [hoy - datetime.timedelta(days=i) for i in range(dias - 1, -1, -1)]
    indice = {f: i for i, f in enumerate(fechas)}
    valores: dict[str, list[int]] = {}
    for fila in ConteoProcedencia.objects.filter(tipo=tipo, fecha__gte=fechas[0]):
        valores.setdefault(fila.valor, [0] * dias)[indice[fila.fecha]] = fila.cantidad
    ordenados = sorted(valores.items(), key=lambda kv: -sum(kv[1]))
    series = ordenados[:top]
    if resto := ordenados[top:]:
        series.append(("otros", [sum(col) for col in zip(*(v for _, v in resto))]))
    return {"fechas": [str(f) for f in fechas], "series": series}
