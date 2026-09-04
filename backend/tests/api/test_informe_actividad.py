"""El informe diario: que llegue aunque algo falle, y que no cuente el staging.

Lo que se prueba acá es sobre todo lo que NO tiene que pasar: que una fuente
caída no impida el mail, que una interpretación fallida no se lleve los
números, y que los eventos del staging —que comparten la key de PostHog con
producción— no entren en el conteo.
"""

import pytest

from api import informe_actividad as informe

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.POSTHOG_PERSONAL_API_KEY = "phx_de_prueba"
    settings.POSTHOG_PROJECT_ID = "528402"
    settings.POSTHOG_API_HOST = "https://us.posthog.com"
    settings.GSC_CLIENT_ID = ""
    settings.GSC_CLIENT_SECRET = ""
    settings.GSC_REFRESH_TOKEN = ""
    settings.GSC_SITE_URL = ""
    settings.RESEND_API_KEY = "re_de_prueba"
    settings.INFORME_DESTINO = "alguien@example.com"
    settings.MAIL_FROM = "info@astraguia.com"
    settings.ANTHROPIC_API_KEY = ""


@pytest.fixture
def posthog_responde(monkeypatch):
    """Captura las consultas que se le mandan a PostHog."""
    consultas = []

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [["pagina_vista", 3, 2]]}

    def post(url, **kwargs):
        consultas.append({"url": url, "json": kwargs.get("json")})
        return _Resp()

    monkeypatch.setattr(informe.httpx, "post", post)
    return consultas


def test_las_consultas_excluyen_el_staging(posthog_responde):
    """La key de PostHog es la misma en los dos entornos: sin este filtro, una
    compra de prueba con la 4242 cuenta como venta real."""
    informe.actividad_del_sitio()

    sql = posthog_responde[0]["json"]["query"]["query"]
    assert "entorno" in sql and "produccion" in sql
    assert "localhost" in sql  # los eventos viejos no traen `entorno`


def test_sin_clave_de_lectura_la_fuente_se_declara_caida(settings):
    """La key del sitio sólo escribe: sin la personal no hay nada que leer."""
    settings.POSTHOG_PERSONAL_API_KEY = ""
    with pytest.raises(informe.FuenteCaida):
        informe.actividad_del_sitio()


def test_search_console_sin_credenciales_no_rompe_el_informe(monkeypatch):
    """La fuente que falta se nombra en el mail; el mail sale igual."""
    enviados = []

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [["pagina_vista", 3, 2]], "id": "email_1"}

    def post(url, **kwargs):
        enviados.append({"url": url, "json": kwargs.get("json")})
        return _Resp()

    monkeypatch.setattr(informe.httpx, "post", post)

    resultado = informe.generar_y_enviar()

    assert resultado["enviado"] is True
    assert any("Search Console" in f for f in resultado["fallas"])
    mail = [e for e in enviados if "resend" in e["url"]][0]
    assert "No se pudo consultar" in mail["json"]["html"]
    assert mail["json"]["to"] == ["alguien@example.com"]


def test_si_falla_la_redaccion_los_numeros_llegan_igual(monkeypatch):
    """La interpretación es la ayuda; el dato es el informe."""
    enviados = []

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [["carta_calculada", 5, 4]], "id": "email_1"}

    monkeypatch.setattr(
        informe.httpx, "post",
        lambda url, **kw: (enviados.append({"url": url, "json": kw.get("json")}), _Resp())[1],
    )
    monkeypatch.setattr(
        informe, "redactar", lambda datos: (_ for _ in ()).throw(RuntimeError("modelo caído")),
    )

    resultado = informe.generar_y_enviar()

    assert resultado["enviado"] is True
    html = [e for e in enviados if "resend" in e["url"]][0]["json"]["html"]
    assert "carta_calculada" in html
    assert "no se pudo redactar" in html


def test_sin_destinatario_no_manda_pero_no_falla(settings, posthog_responde):
    """En desarrollo no hay a dónde mandarlo, y eso no es un error."""
    settings.INFORME_DESTINO = ""
    resultado = informe.generar_y_enviar()
    assert resultado["enviado"] is False


def test_dice_QUE_credencial_falta(settings):
    """Nombrar la variable que falta ahorra la mitad del diagnóstico."""
    settings.GSC_SITE_URL = "sc-domain:astraguia.com"
    settings.GSC_CLIENT_ID = "id"
    settings.GSC_CLIENT_SECRET = ""
    settings.GSC_REFRESH_TOKEN = ""
    with pytest.raises(informe.FuenteCaida) as e:
        informe.busquedas()
    assert "GSC_CLIENT_SECRET" in str(e.value)
    assert "GSC_REFRESH_TOKEN" in str(e.value)


def test_un_refresh_token_revocado_dice_como_arreglarlo(settings, monkeypatch):
    """Google caduca los refresh token a los seis meses sin uso, y revocarlos es
    un clic en la cuenta. Sin este mensaje, el informe diría "400"."""
    settings.GSC_SITE_URL = "sc-domain:astraguia.com"
    settings.GSC_CLIENT_ID = "id"
    settings.GSC_CLIENT_SECRET = "secreto"
    settings.GSC_REFRESH_TOKEN = "viejo"

    class _Rechazo:
        status_code = 400

        def json(self):
            return {"error": "invalid_grant"}

    monkeypatch.setattr(informe.httpx, "post", lambda url, **kw: _Rechazo())

    with pytest.raises(informe.FuenteCaida) as e:
        informe.busquedas()
    assert "autorizar_search_console" in str(e.value)


def test_la_ventana_de_google_termina_en_el_pasado(settings, monkeypatch):
    """Google publica con atraso: pedir "ayer" devuelve cero, y ese cero miente."""
    settings.GSC_SITE_URL = "sc-domain:astraguia.com"
    settings.GSC_CLIENT_ID = "id"
    settings.GSC_CLIENT_SECRET = "secreto"
    settings.GSC_REFRESH_TOKEN = "token"
    monkeypatch.setattr(informe, "_token_google", lambda: "token")

    pedidos = []

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"rows": []}

    monkeypatch.setattr(
        informe.httpx, "post",
        lambda url, **kw: (pedidos.append(kw.get("json")), _Resp())[1],
    )

    import datetime
    resultado = informe.busquedas(dias=7)

    hasta = datetime.date.fromisoformat(pedidos[0]["endDate"])
    assert (datetime.date.today() - hasta).days == informe.DIAS_DE_ATRASO_GSC
    assert "a" in resultado["ventana"]


def test_la_clave_publica_de_posthog_se_detecta_antes_de_pedir(settings):
    """`phc_` y `phx_` se parecen y hacen lo contrario.

    La pública sólo escribe eventos, y pegarla acá devuelve un 403 que dice
    "invalid": no que la clave sea de otro tipo. Pasó el 04-09-2026.
    """
    settings.POSTHOG_PERSONAL_API_KEY = "phc_yymDS7SQcxS5aQojsKUKcvrTMAQ2b4YyMr"
    with pytest.raises(informe.FuenteCaida) as e:
        informe.actividad_del_sitio()
    assert "phx_" in str(e.value)
