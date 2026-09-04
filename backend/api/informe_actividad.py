"""El informe diario de actividad: qué pasó en el sitio, leído y resumido.

Junta lo que miden las dos fuentes que existen —PostHog para lo que pasa dentro
del sitio, Search Console para lo que pasa antes de entrar—, se lo da a Claude
para que lo lea, y manda el resultado por mail.

**Por qué vive acá y no en una tarea programada de Claude Code:** este
repositorio es público, así que las claves de LECTURA de PostHog y de Google no
pueden viajar en él; tienen que estar en las variables del despliegue, que es
donde ya viven las demás. Y acá reusa tres cosas que hace días que funcionan:
el cron de Coolify, el Resend que manda los avisos de compra y el cliente de
Anthropic que escribe los informes natales.

**Nunca propaga una excepción hacia afuera de `generar_y_enviar`.** Es un
informe: que falle una fuente no puede impedir que lleguen las otras, y que
falle entero no puede dejar el cron en rojo eternamente. Lo que falla se dice
DENTRO del mail —"Search Console: no se pudo consultar"—, que es la única forma
de que se entere alguien.

**Retraso de Search Console:** publica con dos o tres días de atraso. El
informe pide la ventana que termina hace tres días y lo dice explícitamente,
para que nadie lea "0 impresiones" como si fuera lo de ayer.
"""

import datetime
import json
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

#: Search Console publica con 2-3 días de atraso: pedir "ayer" devuelve vacío.
DIAS_DE_ATRASO_GSC = 3

_SCOPE_GSC = "https://www.googleapis.com/auth/webmasters.readonly"
_TOKEN_URL = "https://oauth2.googleapis.com/token"

MODELO = "claude-sonnet-5"


class FuenteCaida(Exception):
    """Una fuente no contestó. Se cuenta en el informe, no rompe el envío."""


# --- PostHog ----------------------------------------------------------------


def _consultar_posthog(sql: str) -> list[list]:
    """Una consulta HogQL con la clave PERSONAL, que es la que puede leer.

    `NEXT_PUBLIC_POSTHOG_KEY` sólo escribe eventos: leerlos necesita una
    Personal API Key, que es otra cosa y vive sólo en el despliegue.
    """
    if not settings.POSTHOG_PERSONAL_API_KEY or not settings.POSTHOG_PROJECT_ID:
        raise FuenteCaida("PostHog sin credenciales de lectura")

    respuesta = httpx.post(
        f"{settings.POSTHOG_HOST.rstrip('/')}/api/projects/"
        f"{settings.POSTHOG_PROJECT_ID}/query/",
        headers={"Authorization": f"Bearer {settings.POSTHOG_PERSONAL_API_KEY}"},
        json={"query": {"kind": "HogQLQuery", "query": sql}},
        timeout=_TIMEOUT,
    )
    respuesta.raise_for_status()
    return respuesta.json().get("results", [])


def actividad_del_sitio(dias: int = 1) -> dict:
    """Eventos por tipo, y de dónde salieron.

    Excluye el staging: comparte la key de PostHog con producción a propósito
    —es espejo— y sus eventos llevan `entorno`. Los de antes del 04-09-2026 no
    lo llevan, así que también se descarta lo que venga de `localhost`.
    """
    filtro_entorno = (
        "and coalesce(properties.entorno, 'produccion') = 'produccion' "
        "and not like(coalesce(properties.$current_url, ''), '%localhost%')"
    )
    eventos = _consultar_posthog(f"""
        select event, count() as n, count(distinct distinct_id) as personas
        from events
        where timestamp > now() - interval {int(dias)} day {filtro_entorno}
        group by event order by n desc
    """)
    paginas = _consultar_posthog(f"""
        select properties.ruta as ruta, count() as n
        from events
        where event = 'pagina_vista' and timestamp > now() - interval {int(dias)} day
          {filtro_entorno}
        group by ruta order by n desc limit 12
    """)
    return {
        "eventos": [{"evento": e[0], "veces": e[1], "personas": e[2]} for e in eventos],
        "paginas": [{"ruta": p[0], "veces": p[1]} for p in paginas],
    }


# --- Search Console ---------------------------------------------------------


def _token_google() -> str:
    """Un access token a partir de la service account, sin `google-auth`.

    Es un JWT firmado con la clave privada de la cuenta de servicio, canjeado
    por un token. `pyjwt[crypto]` ya es dependencia del proyecto (lo usa el
    login con Apple), así que esto no agrega ninguna librería.
    """
    if not settings.GSC_CREDENCIALES:
        raise FuenteCaida("Search Console sin credenciales")

    import jwt  # local: sólo lo necesita esta rama

    try:
        cuenta = json.loads(settings.GSC_CREDENCIALES)
    except ValueError as exc:
        raise FuenteCaida(f"GSC_CREDENCIALES no es JSON válido: {exc}") from exc

    ahora = int(datetime.datetime.now(datetime.UTC).timestamp())
    afirmacion = jwt.encode(
        {
            "iss": cuenta["client_email"],
            "scope": _SCOPE_GSC,
            "aud": _TOKEN_URL,
            "iat": ahora,
            "exp": ahora + 3600,
        },
        cuenta["private_key"],
        algorithm="RS256",
    )
    respuesta = httpx.post(
        _TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": afirmacion,
        },
        timeout=_TIMEOUT,
    )
    respuesta.raise_for_status()
    return respuesta.json()["access_token"]


def busquedas(dias: int = 7) -> dict:
    """Impresiones, clics y las consultas que traen gente.

    La ventana termina hace `DIAS_DE_ATRASO_GSC` días porque Google todavía no
    publicó lo más reciente: pedirlo devuelve cero y ese cero no significa nada.
    """
    if not settings.GSC_SITE_URL:
        raise FuenteCaida("Search Console sin propiedad configurada")

    hasta = datetime.date.today() - datetime.timedelta(days=DIAS_DE_ATRASO_GSC)
    desde = hasta - datetime.timedelta(days=dias - 1)
    token = _token_google()

    def pedir(dimensiones: list[str], limite: int) -> list[dict]:
        respuesta = httpx.post(
            "https://searchconsole.googleapis.com/webmasters/v3/sites/"
            f"{httpx.URL(settings.GSC_SITE_URL)}/searchAnalytics/query",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "startDate": desde.isoformat(),
                "endDate": hasta.isoformat(),
                "dimensions": dimensiones,
                "rowLimit": limite,
            },
            timeout=_TIMEOUT,
        )
        respuesta.raise_for_status()
        return respuesta.json().get("rows", [])

    consultas = pedir(["query"], 15)
    paginas = pedir(["page"], 10)
    return {
        "ventana": f"{desde.isoformat()} a {hasta.isoformat()}",
        "impresiones": sum(f.get("impressions", 0) for f in consultas),
        "clics": sum(f.get("clicks", 0) for f in consultas),
        "consultas": [
            {
                "consulta": f["keys"][0],
                "impresiones": f.get("impressions", 0),
                "clics": f.get("clicks", 0),
                "posicion": round(f.get("position", 0), 1),
            }
            for f in consultas
        ],
        "paginas": [
            {"pagina": f["keys"][0], "impresiones": f.get("impressions", 0),
             "clics": f.get("clicks", 0)}
            for f in paginas
        ],
    }


# --- La lectura -------------------------------------------------------------

_SISTEMA = """Sos el analista de ASTRA, un sitio que calcula cartas natales y
vende informes. Escribís para su único desarrollador, que lee esto en el mail a
la mañana.

El sitio es MUY chico: unidades de visitas por día, y todavía casi nada de
ventas. Eso no es un problema a resolver en cada informe: es el punto de
partida. No infieras tendencias de dos visitas ni recomiendes acciones de
manual ("optimizá la conversión", "hacé A/B testing") que no tienen sentido a
esta escala.

Reglas:
- Si no pasó nada digno de mención, decilo en una línea y terminá. Un informe
  corto es un buen informe.
- Señalá lo que CAMBIÓ respecto de lo que venía pasando, no lo que hay.
- Si un número es raro, decí qué lo explicaría y qué habría que mirar.
- Nada de felicitaciones ni de relleno. Prosa directa, en español rioplatense.
- Máximo 200 palabras."""


def redactar(datos: dict) -> str:
    """Le da los números a Claude para que diga qué pasó.

    Si no hay clave o el modelo falla, el informe sale igual con los números
    crudos: el mail tiene que llegar aunque la interpretación no.
    """
    if not settings.ANTHROPIC_API_KEY:
        return "(sin ANTHROPIC_API_KEY: van los números sin lectura)"

    import anthropic

    cliente = anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=httpx.Timeout(60.0, connect=10.0),
    )
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=600,
        system=_SISTEMA,
        messages=[{
            "role": "user",
            "content": (
                "Estos son los datos de hoy. Escribí el informe.\n\n"
                + json.dumps(datos, ensure_ascii=False, indent=1)
            ),
        }],
    )
    return "".join(bloque.text for bloque in respuesta.content if bloque.type == "text")


# --- El mail ----------------------------------------------------------------


def _html(cuerpo: str, datos: dict, fallas: list[str]) -> str:
    """El informe, con la lectura arriba y los números crudos abajo.

    Los números van SIEMPRE, aunque la lectura haya fallado: son el dato, y la
    interpretación es la ayuda.
    """
    def tabla(titulo: str, filas: list[str]) -> str:
        if not filas:
            return f"<h3>{titulo}</h3><p>—</p>"
        return f"<h3>{titulo}</h3><ul>{''.join(f'<li>{f}</li>' for f in filas)}</ul>"

    sitio = datos.get("sitio") or {}
    seo = datos.get("busquedas") or {}

    partes = [
        "<div style='font-family:system-ui,sans-serif;max-width:640px;line-height:1.5'>",
        f"<p style='white-space:pre-wrap'>{cuerpo}</p>",
        "<hr>",
        tabla("En el sitio (últimas 24 h)", [
            f"{e['evento']}: {e['veces']} ({e['personas']} personas)"
            for e in sitio.get("eventos", [])
        ]),
        tabla("Páginas más vistas", [
            f"{p['ruta']}: {p['veces']}" for p in sitio.get("paginas", [])
        ]),
    ]
    if seo:
        partes.append(
            f"<h3>En Google ({seo.get('ventana', '')})</h3>"
            f"<p>{seo.get('impresiones', 0)} impresiones, {seo.get('clics', 0)} clics. "
            f"Google publica con {DIAS_DE_ATRASO_GSC} días de atraso: esto no es lo de ayer.</p>"
        )
        partes.append(tabla("Búsquedas que te muestran", [
            f"{c['consulta']}: {c['impresiones']} impresiones, {c['clics']} clics, "
            f"posición {c['posicion']}"
            for c in seo.get("consultas", [])
        ]))
    if fallas:
        partes.append(tabla("No se pudo consultar", fallas))
    partes.append("</div>")
    return "".join(partes)


def generar_y_enviar() -> dict:
    """Junta, interpreta y manda. Devuelve lo que hizo, para el log del cron.

    No levanta: una fuente caída se anota y el mail sale igual con el resto.
    """
    datos: dict = {}
    fallas: list[str] = []

    for nombre, clave, fn in (
        ("PostHog", "sitio", actividad_del_sitio),
        ("Search Console", "busquedas", busquedas),
    ):
        try:
            datos[clave] = fn()
        except FuenteCaida as exc:
            fallas.append(f"{nombre}: {exc}")
            logger.warning("informe diario sin %s: %s", nombre, exc)
        except Exception as exc:  # noqa: BLE001 — el informe sale igual
            fallas.append(f"{nombre}: {type(exc).__name__}")
            logger.exception("informe diario: %s no contestó", nombre)

    try:
        cuerpo = redactar(datos)
    except Exception as exc:  # noqa: BLE001 — los números importan más
        cuerpo = f"(no se pudo redactar la lectura: {type(exc).__name__})"
        logger.exception("informe diario: falló la redacción")

    if not settings.RESEND_API_KEY or not settings.INFORME_DESTINO:
        logger.info("informe diario sin destino: queda en el log")
        return {"enviado": False, "fallas": fallas, "cuerpo": cuerpo}

    hoy = datetime.date.today().isoformat()
    respuesta = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json={
            "from": settings.MAIL_FROM,
            "to": [settings.INFORME_DESTINO],
            "subject": f"ASTRA — actividad del {hoy}",
            "html": _html(cuerpo, datos, fallas),
        },
        timeout=_TIMEOUT,
    )
    respuesta.raise_for_status()
    logger.info("informe diario enviado", extra={"fallas": fallas})
    return {"enviado": True, "fallas": fallas, "cuerpo": cuerpo}
