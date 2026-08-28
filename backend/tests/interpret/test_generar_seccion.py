from interpret.generator import build_seccion
from interpret.prompts import SECCIONES


class ClienteFalso:
    """Captura lo que se le manda al modelo y devuelve un texto fijo."""

    def __init__(self):
        self.llamadas = []
        self.messages = self

    def create(self, **kwargs):
        self.llamadas.append(kwargs)

        class R:
            content = [type("B", (), {"text": "texto de la sección"})()]

        return R()


def test_la_primera_seccion_no_recibe_contexto_previo():
    c = ClienteFalso()
    build_seccion({"planets": []}, SECCIONES[0], "es", "", c)
    enviado = c.llamadas[0]["messages"][0]["content"]
    assert "YA ESCRITO" not in enviado


def test_las_siguientes_reciben_lo_ya_escrito_para_no_repetirse():
    c = ClienteFalso()
    build_seccion({"planets": []}, SECCIONES[2], "es", "Ya se habló del Sol en Leo.", c)
    enviado = c.llamadas[0]["messages"][0]["content"]
    assert "Ya se habló del Sol en Leo." in enviado


def test_el_foco_de_la_seccion_viaja_en_el_pedido():
    c = ClienteFalso()
    build_seccion({"planets": []}, SECCIONES[1], "es", "", c)
    enviado = c.llamadas[0]["messages"][0]["content"]
    assert "Mercurio" in enviado


def test_devuelve_el_texto_del_modelo():
    assert build_seccion({"planets": []}, SECCIONES[0], "es", "", ClienteFalso()) == "texto de la sección"


def test_el_tope_de_tokens_acompana_al_largo_pedido():
    c = ClienteFalso()
    build_seccion({"planets": []}, SECCIONES[4], "es", "", c)  # tensiones: 1000 palabras
    assert c.llamadas[0]["max_tokens"] >= 1000 * 2
