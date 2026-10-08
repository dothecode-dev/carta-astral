"""Juez + reparación del trato (interpret/revision_trato.py).

Medido en staging el 08-10: un informe neutro salió con «podés generar vos
misma el sacudón» pese a la instrucción. Cada sección pasa por un juez que
lista los fragmentos con el género equivocado y, si hay, por una reparación
acotada que se verifica antes de aceptarla. La revisión nunca hace fallar un
informe: ante cualquier duda devuelve el texto original.
"""

import json
import logging

import anthropic
import httpx
import pytest

from interpret import revision_trato
from interpret.prompts import MODEL
from interpret.revision_trato import revisar_trato
from interpret.trato import instruccion

TEXTO = (
    "## Tu motor\n\n"
    "Marte en Aries te da un empuje que no espera permiso. Cuando algo se "
    "estanca, podés generar vos misma el sacudón que hace falta, y eso te "
    "vuelve una persona capaz de abrir caminos donde otros ven paredes. La "
    "Luna en Cáncer, en cambio, es tranquila y protectora con lo propio.\n\n"
    "## Tu forma de pensar\n\n"
    "Mercurio en Géminis te lleva a saltar de un tema a otro con curiosidad, "
    "sin convertirte en especialista de una sola cosa. Leés, preguntás, "
    "conectás ideas que nadie había juntado, y en esa mezcla aparece lo más "
    "tuyo: la capacidad de traducir lo complejo en algo que se entiende. "
    "Trabajar así no tiene por qué ser una pelea constante contra vos.\n\n"
    "A veces vas a sentirte confundida ante tanto estímulo, y vas a preguntarte "
    "cómo estás armado: la manera en que reaccionás dice mucho."
)
FRAG = "generar vos misma el sacudón"
FRAG_OK = "generar por tu cuenta el sacudón"
REPARADO = TEXTO.replace(FRAG, FRAG_OK)


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason
        self.usage = None


class _StreamCtx:
    def __init__(self, resultado):
        self._resultado = resultado

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if isinstance(self._resultado, BaseException):
            raise self._resultado
        return self._resultado


class ClienteFalso:
    """Devuelve las respuestas en orden (texto o excepción) y registra los
    kwargs de cada `messages.stream(...)`: la interfaz real que usa
    `generator._stream_text`."""

    def __init__(self, *respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []

    class _Messages:
        def __init__(self, outer):
            self.outer = outer

        def stream(self, **kwargs):
            self.outer.llamadas.append(kwargs)
            if not self.outer._respuestas:
                raise AssertionError("llamada al modelo que el test no esperaba")
            r = self.outer._respuestas.pop(0)
            return _StreamCtx(r if isinstance(r, (BaseException, _Resp)) else _Resp(r))

    @property
    def messages(self):
        return ClienteFalso._Messages(self)


def _juez(*fragmentos):
    return json.dumps({"fragmentos": list(fragmentos)}, ensure_ascii=False)


def _reemplazos(*pares):
    return json.dumps(
        {"reemplazos": [{"original": o, "corregido": c} for o, c in pares]}, ensure_ascii=False
    )


def _system(llamada):
    return "\n".join(b["text"] for b in llamada["system"])


# --- cuándo no se llama a nada ---


@pytest.mark.parametrize("trato", ["femenino", "masculino", "neutro", ""])
def test_ingles_no_llama_al_modelo(trato):
    cliente = ClienteFalso()
    assert revisar_trato(TEXTO, trato, "en", cliente) == TEXTO
    assert cliente.llamadas == []


def test_juez_sin_fragmentos_no_repara():
    cliente = ClienteFalso(_juez())
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert len(cliente.llamadas) == 1


# --- el camino feliz ---


def test_reemplaza_el_fragmento_y_nada_mas(caplog):
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG_OK)), _juez())
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        resultado = revisar_trato(TEXTO, "neutro", "es", cliente)
    assert resultado == REPARADO
    # Fuera del fragmento, byte-idéntico.
    i = TEXTO.index(FRAG)
    assert resultado[:i] == TEXTO[:i]
    assert resultado[i + len(FRAG_OK):] == TEXTO[i + len(FRAG):]
    # Se loguean números, no texto.
    resumen = [r.getMessage() for r in caplog.records if "listados=" in r.getMessage()]
    assert resumen and "listados=1" in resumen[0] and "aplicados=1" in resumen[0]
    assert "sacudón" not in resumen[0]


def test_la_reparacion_recibe_los_fragmentos_con_contexto_y_no_el_texto_entero():
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG_OK)), _juez())
    revisar_trato(TEXTO, "neutro", "es", cliente)
    reparacion = cliente.llamadas[1]
    contenido = reparacion["messages"][0]["content"]
    assert FRAG in contenido
    assert "se estanca, podés" in contenido  # contexto de antes
    assert TEXTO not in contenido
    assert instruccion("neutro", "es") in _system(reparacion)
    formato = reparacion["output_config"]["format"]
    assert formato["type"] == "json_schema"
    assert formato["schema"]["required"] == ["reemplazos"]


def test_juez_con_bloque_json_tambien_se_entiende():
    cliente = ClienteFalso(f"```json\n{_juez(FRAG)}\n```", _reemplazos((FRAG, FRAG_OK)), _juez())
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == REPARADO


def test_fragmentos_que_no_estan_en_el_texto_se_descartan():
    """Un fragmento que el juez inventó no se le pide reparar a nadie."""
    cliente = ClienteFalso(_juez("esto no está en el texto"))
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert len(cliente.llamadas) == 1


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_las_dos_llamadas_van_sin_razonamiento_y_con_el_modelo_de_generacion(lang):
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG_OK)), _juez())
    revisar_trato(TEXTO, "femenino", lang, cliente)
    assert len(cliente.llamadas) == 3  # juez, reparación, juez de la segunda vuelta
    for llamada in cliente.llamadas:
        assert llamada["model"] == MODEL
        assert llamada["thinking"] == {"type": "disabled"}


def test_el_juez_pide_salida_estructurada_con_techo_chico():
    cliente = ClienteFalso(_juez())
    revisar_trato(TEXTO, "neutro", "es", cliente)
    juez = cliente.llamadas[0]
    assert juez["max_tokens"] == 1000
    formato = juez["output_config"]["format"]
    assert formato["type"] == "json_schema"
    assert formato["schema"]["required"] == ["fragmentos"]
    assert TEXTO in juez["messages"][0]["content"]


@pytest.mark.parametrize(
    ("trato", "esperado", "ausente"),
    [
        ("femenino", "femenino", "masculino"),
        ("masculino", "masculino", "femenino"),
        ("neutro", "neutro", None),
        ("", "neutro", None),
    ],
)
def test_el_system_del_juez_nombra_el_trato(trato, esperado, ausente):
    cliente = ClienteFalso(_juez())
    revisar_trato(TEXTO, trato, "es", cliente)
    system = _system(cliente.llamadas[0])
    assert revision_trato.describir_trato(trato) in system
    assert esperado in revision_trato.describir_trato(trato)
    if ausente:
        assert ausente not in revision_trato.describir_trato(trato)


# --- pares que se descartan (el resto se aplica igual) ---


def test_un_par_que_introduce_vos_mismo_se_rechaza_y_el_otro_se_aplica(caplog):
    """Medido en staging: la reparación pasó «contra vos» a «contra vos mismo»."""
    contra = "una pelea constante contra vos"
    cliente = ClienteFalso(
        _juez(FRAG, contra),
        _reemplazos((FRAG, FRAG_OK), (contra, "una pelea constante contra vos mismo")),
        _juez(),
    )
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == REPARADO
    resumen = [r.getMessage() for r in caplog.records if "listados=" in r.getMessage()][0]
    assert "aplicados=1" in resumen and "forma_prohibida=1" in resumen


def test_un_par_cuyo_original_no_listo_el_juez_se_descarta(caplog):
    otro = "Mercurio en Géminis"
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((otro, "Mercurio en Cáncer"), (FRAG, FRAG_OK)), _juez())
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == REPARADO
    resumen = [r.getMessage() for r in caplog.records if "listados=" in r.getMessage()][0]
    assert "no_listado=1" in resumen


def test_un_par_identico_se_descarta():
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG)))
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO


def test_un_par_con_salto_de_linea_se_descarta():
    frag = "## Tu motor\n\nMarte en Aries"
    cliente = ClienteFalso(_juez(frag), _reemplazos((frag, "## Tu impulso\n\nMarte en Aries")))
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO


@pytest.mark.parametrize(
    ("trato", "corregido", "rechazado"),
    [
        ("neutro", "generar vos misma el sacudón con calma", True),
        ("neutro", "generar por tu cuenta el sacudón", False),
        ("neutro", "gerar você mesmo o sacudón", True),
        ("neutro", "generar lo mismo de siempre", True),
        ("femenino", "generar vos mismo el sacudón", True),
        ("femenino", "generar por tu cuenta el sacudón", False),
        ("masculino", "generar vos misma ese sacudón", True),
        ("masculino", "generar vos mismo el sacudón", False),
        ("femenino", "gerar você mesmo o sacudón", True),
        ("masculino", "gerar você mesma o sacudón", True),
    ],
)
def test_formas_prohibidas_segun_el_trato(trato, corregido, rechazado):
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, corregido)), _juez())
    resultado = revisar_trato(TEXTO, trato, "es", cliente)
    assert resultado == (TEXTO if rechazado else TEXTO.replace(FRAG, corregido))


def test_reparacion_sin_reemplazos_devuelve_el_original():
    cliente = ClienteFalso(_juez(FRAG), _reemplazos())
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO


# --- fallos del LLM o JSON roto: el original ---


@pytest.mark.parametrize(
    "respuesta",
    ["esto no es json", '{"otra_cosa": []}', '{"fragmentos": "no es lista"}', '{"fragmentos": [1, 2]}'],
)
def test_juez_con_respuesta_ilegible_devuelve_el_original_y_loguea(respuesta, caplog):
    cliente = ClienteFalso(respuesta)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert len(cliente.llamadas) == 1
    assert any(r.levelno == logging.WARNING for r in caplog.records)


@pytest.mark.parametrize(
    "respuesta",
    [
        "esto no es json",
        '{"reemplazos": "no es lista"}',
        '{"reemplazos": [{"original": "x"}]}',
        '{"reemplazos": [{"original": 1, "corregido": 2}]}',
        _Resp('{"reemplazos": [', stop_reason="max_tokens"),
    ],
)
def test_reparacion_ilegible_devuelve_el_original_y_loguea(respuesta, caplog):
    cliente = ClienteFalso(_juez(FRAG), respuesta)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_error_del_llm_en_el_juez_devuelve_el_original_y_loguea(caplog):
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    cliente = ClienteFalso(error)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_error_del_llm_en_la_reparacion_devuelve_el_original_y_loguea(caplog):
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    cliente = ClienteFalso(_juez(FRAG), error)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# --- marcas inclusivas: rechazadas en todos los tratos ---


@pytest.mark.parametrize("trato", ["femenino", "masculino", "neutro"])
@pytest.mark.parametrize(
    ("original", "corregido"),
    [
        ("sentirte confundida", "sentirte confundido/a"),
        ("sentirte confundida", "sentirte confundid@"),
        ("sentirte confundida", "sentirte confundidx"),
        ("sentirte confundida", "sentirlo con todxs"),
    ],
)
def test_marcas_inclusivas_se_rechazan(trato, original, corregido):
    """Medido en staging: «sentirte confundida» → «sentirte confundido/a»."""
    cliente = ClienteFalso(_juez(original), _reemplazos((original, corregido)))
    assert revisar_trato(TEXTO, trato, "es", cliente) == TEXTO


def test_una_palabra_en_x_que_ya_estaba_en_el_original_no_se_rechaza():
    texto = TEXTO + "\n\nNecesitás algo del relax para no sentirte sola."
    original = "del relax para no sentirte sola"
    corregido = "del relax para no sentirte sin compañía"
    cliente = ClienteFalso(_juez(original), _reemplazos((original, corregido)), _juez())
    assert revisar_trato(texto, "neutro", "es", cliente) == texto.replace(original, corregido)


# --- segunda vuelta acotada ---

CONF = "sentirte confundida ante"
CONF_OK = "sentir confusión ante"
ARMADO = "cómo estás armado: la manera"
ARMADO_OK = "cómo te armaste: la manera"
ARMADO_DENTRO = "cómo estás armado por dentro: la manera"


def test_una_segunda_vuelta_corrige_lo_que_quedo(caplog):
    cliente = ClienteFalso(
        _juez(FRAG, ARMADO),
        # Medido en staging: la primera reparación agregó palabras y dejó el
        # género. Se rechaza, y la segunda vuelta lo corrige.
        _reemplazos((FRAG, FRAG_OK), (ARMADO, ARMADO_DENTRO)),
        _juez(ARMADO),
        _reemplazos((ARMADO, ARMADO_OK)),
    )
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        resultado = revisar_trato(TEXTO, "neutro", "es", cliente)
    assert resultado == TEXTO.replace(FRAG, FRAG_OK).replace(ARMADO, ARMADO_OK)
    assert len(cliente.llamadas) == 4
    vueltas = [r.getMessage() for r in caplog.records if "listados=" in r.getMessage()]
    assert "vuelta=1" in vueltas[0] and "vuelta=2" in vueltas[1]


def test_la_segunda_reparacion_tampoco_toca_nada_fuera_de_los_fragmentos():
    cliente = ClienteFalso(
        _juez(FRAG),
        _reemplazos((FRAG, FRAG_OK)),
        _juez(CONF),
        _reemplazos((CONF, CONF_OK), ("Marte en Aries", "Marte en Tauro")),
    )
    resultado = revisar_trato(TEXTO, "neutro", "es", cliente)
    assert resultado == TEXTO.replace(FRAG, FRAG_OK).replace(CONF, CONF_OK)


def test_se_corta_despues_de_dos_vueltas():
    """Aunque en la segunda vuelta se aplique algo, no hay un tercer juez:
    el cliente falso levanta si se le pide una llamada de más."""
    cliente = ClienteFalso(
        _juez(FRAG),
        _reemplazos((FRAG, FRAG_OK)),
        _juez(CONF),
        _reemplazos((CONF, CONF_OK)),
    )
    resultado = revisar_trato(TEXTO, "neutro", "es", cliente)
    assert resultado == TEXTO.replace(FRAG, FRAG_OK).replace(CONF, CONF_OK)
    assert len(cliente.llamadas) == 4


def test_sin_pares_aplicados_no_hay_segunda_vuelta():
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG)))
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert len(cliente.llamadas) == 2


def test_segundo_juez_vacio_no_repara_mas():
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG_OK)), _juez())
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == REPARADO
    assert len(cliente.llamadas) == 3


def test_si_la_segunda_vuelta_falla_queda_lo_de_la_primera(caplog):
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG_OK)), error)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == REPARADO
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_el_system_de_la_reparacion_explica_que_agregar_palabras_no_corrige():
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG)))
    revisar_trato(TEXTO, "neutro", "es", cliente)
    system = _system(cliente.llamadas[1])
    assert "estás hecho" in system and "te armaste" in system
    assert "barras" in system


@pytest.mark.parametrize("trato", ["femenino", "masculino", "neutro"])
def test_una_correccion_que_solo_agrega_palabras_se_rechaza(trato, caplog):
    """Medido en staging: «cómo estás armado: la manera» → «cómo estás armado
    por dentro: la manera». Contiene al original entero: no corrigió nada."""
    cliente = ClienteFalso(_juez(ARMADO), _reemplazos((ARMADO, ARMADO_DENTRO)))
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, trato, "es", cliente) == TEXTO
    resumen = [r.getMessage() for r in caplog.records if "listados=" in r.getMessage()][0]
    assert "solo_agrego_palabras=1" in resumen
    assert len(cliente.llamadas) == 2  # nada aplicado: no hay segunda vuelta


# --- fragmentos que aparecen más de una vez (hallazgo de code review) ---


def test_un_fragmento_repetido_no_se_repara(caplog):
    """`replace(..., 1)` corrige la PRIMERA aparición: si «seguro» está en
    «es seguro que Saturno» y en «estás seguro», tocaría la equivocada."""
    texto = TEXTO + "\n\nEs seguro que Saturno ayuda, y vos estás seguro de eso."
    cliente = ClienteFalso(_juez("seguro"))
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(texto, "neutro", "es", cliente) == texto
    assert len(cliente.llamadas) == 1  # no se pide reparar nada
    assert any("no_unico=1" in r.getMessage() for r in caplog.records)


def test_un_fragmento_repetido_se_descarta_y_el_unico_se_repara():
    texto = TEXTO + "\n\nEs seguro que Saturno ayuda, y vos estás seguro de eso."
    cliente = ClienteFalso(_juez("seguro", FRAG), _reemplazos((FRAG, FRAG_OK)), _juez())
    assert revisar_trato(texto, "neutro", "es", cliente) == texto.replace(FRAG, FRAG_OK)
    assert "fragmento: «seguro»" not in cliente.llamadas[1]["messages"][0]["content"]


def test_en_la_segunda_vuelta_un_original_que_paso_a_aparecer_dos_veces_se_rechaza(caplog):
    """Un corregido ya aplicado puede contener el texto de otro fragmento:
    después de aplicarlo, ese original aparece dos veces y no se toca."""
    conf = "confundida ante"
    armado_con_conf = "cómo te confundida ante: la manera"
    cliente = ClienteFalso(
        _juez(FRAG),
        _reemplazos((FRAG, FRAG_OK)),
        _juez(ARMADO, conf),
        _reemplazos((ARMADO, armado_con_conf), (conf, "con confusión ante")),
    )
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        resultado = revisar_trato(TEXTO, "neutro", "es", cliente)
    assert resultado == TEXTO.replace(FRAG, FRAG_OK).replace(ARMADO, armado_con_conf)
    vuelta2 = [r.getMessage() for r in caplog.records if "vuelta=2 listados=" in r.getMessage()][0]
    assert "aplicados=1" in vuelta2 and "no_unico=1" in vuelta2



# --- la reparación no puede reescribir ni despersonalizar (prueba real, 8ef370d) ---

VIVIS = "Vivís entre esas dos fuerzas, y naciste con una enorme sensibilidad"
TEXTO_VIVIS = TEXTO + "\n\n" + VIVIS + " que no te pida endurecerte en tu camino."


def _resumen(caplog):
    return [r.getMessage() for r in caplog.records if "listados=" in r.getMessage()][0]


def test_el_caso_vivis_entre_esas_dos_se_rechaza(caplog):
    """Medido en staging: la reparación lo despersonalizó."""
    cliente = ClienteFalso(
        _juez(VIVIS),
        _reemplazos((VIVIS, "Hay un vivir entre esas dos fuerzas, y hubo un nacer con una enorme sensibilidad")),
    )
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO_VIVIS, "neutro", "es", cliente) == TEXTO_VIVIS
    resumen = _resumen(caplog)
    assert "despersonaliza=1" in resumen or "cambio_grande=1" in resumen


@pytest.mark.parametrize(
    ("original", "corregido"),
    [
        ("que no te pida endurecerte", "que no pida endurecerse"),
        ("endurecerte en tu camino", "endurecerte en el camino"),
    ],
)
def test_sacar_la_segunda_persona_se_rechaza_por_despersonalizar(original, corregido, caplog):
    cliente = ClienteFalso(_juez(original), _reemplazos((original, corregido)))
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO_VIVIS, "neutro", "es", cliente) == TEXTO_VIVIS
    assert "despersonaliza=1" in _resumen(caplog)


def test_un_cambio_de_mas_de_cuatro_palabras_se_rechaza(caplog):
    corregido = "generar por tu propia cuenta y sin esperar a nadie el sacudón"
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, corregido)))
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert "cambio_grande=1" in _resumen(caplog)


def test_un_fragmento_de_veinte_palabras_se_descarta_por_largo(caplog):
    largo = (
        "Marte en Aries te da un empuje que no espera permiso. Cuando algo "
        "se estanca, podés generar vos misma el"
    )
    assert len(largo.split()) == 20 and TEXTO.count(largo) == 1
    cliente = ClienteFalso(_juez(largo))
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert len(cliente.llamadas) == 1  # no se pide reparar
    assert any("largo=1" in r.getMessage() for r in caplog.records)


def test_vos_misma_el_sacudon_por_tu_cuenta_se_aplica():
    original, corregido = "vos misma el sacudón", "por tu cuenta el sacudón"
    cliente = ClienteFalso(_juez(original), _reemplazos((original, corregido)), _juez())
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO.replace(original, corregido)


def test_contigo_a_con_vos_se_aplica():
    """«con vos» tiene tantas marcas de segunda persona como «contigo»."""
    texto = TEXTO + "\n\nNadie es tan exigente contigo misma como vos."
    original, corregido = "exigente contigo misma", "exigente con vos"
    cliente = ClienteFalso(_juez(original), _reemplazos((original, corregido)), _juez())
    assert revisar_trato(texto, "neutro", "es", cliente) == texto.replace(original, corregido)


@pytest.mark.parametrize(
    ("original", "corregido", "lang", "rechazado"),
    [
        ("você mesma decide", "você decide", "pt", False),
        ("isso a torna sozinha", "isso torna", "pt", False),  # no había marca
        ("seu caminho sozinha", "o caminho", "pt", True),
        ("contigo mesma", "com você", "pt", False),
    ],
)
def test_marcas_de_segunda_persona_en_portugues(original, corregido, lang, rechazado):
    texto = TEXTO + "\n\n" + original + "."
    cliente = ClienteFalso(_juez(original), _reemplazos((original, corregido)), _juez())
    esperado = texto if rechazado else texto.replace(original, corregido)
    assert revisar_trato(texto, "neutro", lang, cliente) == esperado


def test_el_system_de_la_reparacion_pide_segunda_persona_y_pocas_palabras():
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG)))
    revisar_trato(TEXTO, "neutro", "es", cliente)
    system = _system(cliente.llamadas[1])
    assert "segunda persona" in system
    assert "hay un vivir" in system and "hubo un nacer" in system



# --- un par tiene que cambiar una palabra con género (prueba real, 9a22a6e) ---


@pytest.mark.parametrize(
    ("original", "corregido", "lang", "aplicado"),
    [
        ("Vivís entre esas dos", "Transitás entre esas dos", "es", False),
        ("permeabilidad hacia", "apertura hacia", "es", False),
        # Cambian «naciste» y «con»: ninguna tiene género.
        ("naciste con una enorme", "tenés una enorme", "es", False),
        ("vos misma el sacudón", "por tu cuenta el sacudón", "es", True),
        ("estás armado", "te armaste", "es", True),
        ("para ser tomado en serio", "para que te tomen en serio", "es", True),
        ("Áries o empurra", "Áries te empurra", "pt", True),
    ],
)
def test_un_par_sin_palabra_con_genero_cambiada_se_rechaza(original, corregido, lang, aplicado, caplog):
    texto = "## Tu motor\n\nUn párrafo que no tiene nada que corregir.\n\n" + original + "."
    respuestas = [_juez(original), _reemplazos((original, corregido))] + ([_juez()] if aplicado else [])
    cliente = ClienteFalso(*respuestas)
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        resultado = revisar_trato(texto, "neutro", lang, cliente)
    if aplicado:
        assert resultado == texto.replace(original, corregido)
    else:
        assert resultado == texto
        assert "sin_genero=1" in _resumen(caplog)


# --- code review sobre d3f6f1a..a0d5caa ---

BASE = "## Tu motor\n\nUn párrafo que no tiene nada que corregir.\n\n"


@pytest.mark.parametrize(
    ("original", "corregido", "trato", "lang"),
    [
        ("un gran soñador", "una gran soñadora", "femenino", "es"),
        ("el protector", "la protectora", "femenino", "es"),
        ("um sonhador", "uma sonhadora", "femenino", "pt"),
        ("un soñador", "alguien que sueña", "neutro", "es"),
    ],
)
def test_correcciones_reales_con_determinante_o_sufijo_se_aplican(original, corregido, trato, lang):
    """Hallazgo de code review: «sin_genero» rechazaba estas correcciones
    porque sólo miraba -o/-a/-os/-as."""
    texto = BASE + "Sos " + original + " de verdad."
    cliente = ClienteFalso(_juez(original), _reemplazos((original, corregido)), _juez())
    assert revisar_trato(texto, trato, lang, cliente) == texto.replace(original, corregido)


def test_una_frase_repetida_se_descarta_como_no_unico(caplog):
    """Revertido de 19a0287: reemplazar todas las copias cambia subcadenas y
    copias que no se refieren a quien lee. Una frase repetida no se toca."""
    texto = BASE + "Hoy estás cansado de esperar, y mañana estás cansado de correr."
    cliente = ClienteFalso(_juez("estás cansado"))
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(texto, "femenino", "es", cliente) == texto
    assert len(cliente.llamadas) == 1
    assert any("no_unico=1" in r.getMessage() for r in caplog.records)


def test_una_palabra_suelta_repetida_se_sigue_descartando(caplog):
    texto = BASE + "Es seguro que Saturno ayuda, y vos estás seguro de eso."
    cliente = ClienteFalso(_juez("seguro"))
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(texto, "neutro", "es", cliente) == texto
    assert len(cliente.llamadas) == 1
    assert any("no_unico=1" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    ("original", "corregido", "lang"),
    [
        ("sos guardián", "sos guardiana", "es"),
        ("sos bailarín", "sos bailarina", "es"),
        ("sos español", "sos española", "es"),
        ("você é português", "você é portuguesa", "pt"),
    ],
)
def test_terminaciones_an_in_ol_es_cuentan_como_genero(original, corregido, lang):
    texto = BASE + original + " de verdad."
    cliente = ClienteFalso(_juez(original), _reemplazos((original, corregido)), _juez())
    assert revisar_trato(texto, "femenino", lang, cliente) == texto.replace(original, corregido)


# --- palabras completas (code review sobre cf25337) ---


@pytest.mark.parametrize(
    ("texto_extra", "fragmento", "corregido", "lang"),
    [
        ("Sentís que la fuerza del protector te guía.", "el protector", "la protectora", "es"),
        ("Isso agrada ao sonhador que há em você.", "o sonhador", "a sonhadora", "pt"),
    ],
)
def test_un_fragmento_que_solo_aparece_dentro_de_otra_palabra_se_descarta(
    texto_extra, fragmento, corregido, lang, caplog
):
    """Aparece UNA vez como subcadena, nunca como palabras completas: antes
    pasaba el filtro y terminaba como «dla protectora» / «aa sonhadora»."""
    texto = BASE + texto_extra
    assert texto.count(fragmento) == 1
    cliente = ClienteFalso(_juez(fragmento), _reemplazos((fragmento, corregido)), _juez())
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(texto, "femenino", lang, cliente) == texto
    assert len(cliente.llamadas) == 1
    assert any("ausente=1" in r.getMessage() for r in caplog.records)


def test_un_fragmento_en_limite_de_palabra_se_sigue_aplicando():
    texto = BASE + "Sos el protector de todos, y eso te define."
    cliente = ClienteFalso(_juez("el protector"), _reemplazos(("el protector", "la protectora")), _juez())
    assert revisar_trato(texto, "femenino", "es", cliente) == texto.replace("el protector", "la protectora")


def test_el_conteo_de_unicidad_es_por_palabras_completas():
    """«el protector» suelto una vez y dentro de «del protector» otra: como
    palabras completas aparece una sola vez, y se corrige ésa."""
    texto = BASE + "Sos el protector de todos, y la fuerza del protector te guía."
    cliente = ClienteFalso(_juez("el protector"), _reemplazos(("el protector", "la protectora")), _juez())
    esperado = BASE + "Sos la protectora de todos, y la fuerza del protector te guía."
    assert revisar_trato(texto, "femenino", "es", cliente) == esperado


def test_una_barra_invertida_en_el_corregido_no_se_interpreta():
    texto = BASE + "Sos el protector de todos."
    corregido = "la protectora\\1"  # una barra invertida literal
    cliente = ClienteFalso(_juez("el protector"), _reemplazos(("el protector", corregido)), _juez())
    assert revisar_trato(texto, "femenino", "es", cliente) == texto.replace("el protector", corregido)


def test_los_espacios_alrededor_de_fragmentos_y_pares_se_recortan():
    """Code review sobre 51eb89e: «el protector » nunca pasaba el límite de
    palabra y se descartaba como ausente."""
    texto = BASE + "Sos el protector de todos."
    cliente = ClienteFalso(
        _juez("el protector ", "   "),
        _reemplazos((" el protector ", "la protectora "), ("  ", "algo")),
        _juez(),
    )
    assert revisar_trato(texto, "femenino", "es", cliente) == texto.replace("el protector", "la protectora")
