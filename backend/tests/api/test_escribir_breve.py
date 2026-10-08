from api import informe_service


def test_escribe_y_pasa_por_el_juez(monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        informe_service, "build_interpretation",
        lambda data, lang, version, client, trato="": llamadas.append(("build", lang, trato)) or "texto",
    )
    monkeypatch.setattr(
        informe_service, "revisar_trato",
        lambda texto, trato, lang, client: llamadas.append(("juez", texto)) or texto + " revisado",
    )
    assert informe_service.escribir_breve({"a": 1}, "es", "femenino", object()) == "texto revisado"
    assert llamadas == [("build", "es", "femenino"), ("juez", "texto")]
