"""El informe de vínculo de punta a punta, con el lock REAL (la trampa del RF23:
renovar con otra clave aborta tras la primera sección)."""

import pytest

from api import informe_service
from api import interpretation_service as svc
from api.canje import otorgar
from api.models import Interpretation, Movimiento
from api.vinculo_service import crear_vinculo

from tests.api.llm_falso import ClienteFalso

pytestmark = pytest.mark.django_db

A = {"date": "1985-03-14", "time": "08:30", "time_known": True, "lat": -32.95, "lng": -60.65}
B = {"date": "1988-09-09", "time": "06:10", "time_known": True, "lat": -31.42, "lng": -64.18}


@pytest.fixture
def vinculo(make_account, settings, db_cache):
    settings.VINCULO_ENABLED = True
    acc = make_account()
    otorgar(acc, "informe_vinculo", 1, origen="compra", external_id="v:1")
    return crear_vinculo(acc, "trabajo", [{**A, "rol": "jefe"}, {**B, "rol": "equipo"}])


def test_genera_y_traduce_las_ocho_con_el_lock_real(vinculo, monkeypatch):
    cliente = ClienteFalso()
    monkeypatch.setattr(svc, "_build_client", lambda: cliente)
    interp = svc.iniciar_generacion(vinculo, "es", vinculo.account, tier="largo")
    svc.completar_generacion(interp, vinculo.account)
    interp.refresh_from_db()
    assert interp.completa and interp.secciones.count() == 8
    assert interp.content_key
    assert Movimiento.objects.filter(sujeto=vinculo, tipo="consumo", codigo_producto="informe_vinculo").count() == 1

    en = svc.iniciar_generacion(vinculo, "en", vinculo.account, tier="largo")
    svc.completar_generacion(en, vinculo.account)
    en.refresh_from_db()
    assert en.completa and en.secciones.count() == 8 and en.traducido_de_id == interp.pk
    assert Movimiento.objects.filter(sujeto=vinculo, tipo="consumo").count() == 1  # traducir es gratis


def test_el_prompt_es_el_del_vinculo(vinculo, monkeypatch):
    cliente = ClienteFalso()
    monkeypatch.setattr(svc, "_build_client", lambda: cliente)
    interp = svc.iniciar_generacion(vinculo, "es", vinculo.account, tier="largo")
    svc.completar_generacion(interp, vinculo.account)
    primera = cliente.llamadas[0]
    assert "Persona A" in primera["system"][0]["text"]
    assert "jefe o jefa" in primera["messages"][0]["content"]


def test_el_vinculo_no_tiene_lectura_breve(vinculo):
    with pytest.raises(ValueError):
        svc.iniciar_generacion(vinculo, "es", vinculo.account, tier="corto")


def test_agotados_los_intentos_devuelve_el_derecho_del_vinculo(vinculo, monkeypatch):
    monkeypatch.setattr(svc, "_build_client", lambda: ClienteFalso(falla_en=1))
    interp = svc.iniciar_generacion(vinculo, "es", vinculo.account, tier="largo")
    for _ in range(svc.INTENTOS_MAXIMOS):
        interp = Interpretation.objects.filter(pk=interp.pk).first() or interp
        svc.completar_generacion(interp, vinculo.account)
    assert Movimiento.objects.filter(sujeto=None, tipo="consumo", codigo_producto="informe_vinculo").exists()
    assert Movimiento.objects.filter(tipo="devolucion", codigo_producto="informe_vinculo").count() == 1


def test_reanudar_termina_un_vinculo_a_medias(vinculo, monkeypatch):
    from django.core.management import call_command
    monkeypatch.setattr(svc, "_build_client", lambda: ClienteFalso(falla_en=3))
    interp = svc.iniciar_generacion(vinculo, "es", vinculo.account, tier="largo")
    svc.completar_generacion(interp, vinculo.account)
    monkeypatch.setattr(svc, "_build_client", lambda: ClienteFalso())
    call_command("reanudar_informes")
    interp.refresh_from_db()
    assert interp.completa and interp.secciones.count() == 8


def test_el_aviso_de_listo_lleva_a_la_pagina_del_vinculo(vinculo, monkeypatch):
    enviados = []
    monkeypatch.setattr(informe_service.notificaciones, "notificar",
                        lambda acc, evento, ctx, lang: enviados.append(ctx))
    monkeypatch.setattr(svc, "_build_client", lambda: ClienteFalso())
    interp = svc.iniciar_generacion(vinculo, "es", vinculo.account, tier="largo")
    svc.completar_generacion(interp, vinculo.account)
    assert enviados[-1]["ruta"] == f"/vinculo/{vinculo.uuid}"


@pytest.mark.parametrize("generos,modelo", [
    (("femenino", "masculino"), "barato"),
    (("femenino", "neutro"), "caro"),
])
def test_la_traduccion_del_vinculo_va_por_el_traductor_sin_trato(
    make_account, settings, db_cache, monkeypatch, generos, modelo,
):
    """El vínculo está en tercera persona: la instrucción de trato (segunda
    persona del lector) no aplica. Con los dos géneros conocidos va al modelo
    barato; con alguien en neutro, al caro, como el trato neutro del natal
    (medido en staging: Haiku no respeta el neutro)."""
    from interpret.prompts import MODEL, TRANSLATE_MODEL

    settings.VINCULO_ENABLED = True
    acc = make_account()
    otorgar(acc, "informe_vinculo", 1, origen="compra", external_id="v:m")
    s = crear_vinculo(acc, "pareja", [{**A, "genero": generos[0]}, {**B, "genero": generos[1]}])
    monkeypatch.setattr(informe_service, "revisar_personas", lambda texto, *a: texto)
    cliente = ClienteFalso()
    monkeypatch.setattr(svc, "_build_client", lambda: cliente)
    es = svc.iniciar_generacion(s, "es", acc, tier="largo")
    svc.completar_generacion(es, acc)
    antes = len(cliente.llamadas)
    pt = svc.iniciar_generacion(s, "pt", acc, tier="largo")
    svc.completar_generacion(pt, acc)
    traducciones = cliente.llamadas[antes:]
    esperado = TRANSLATE_MODEL if modelo == "barato" else MODEL
    assert traducciones and all(c["model"] == esperado for c in traducciones)


def test_cada_seccion_pasa_por_el_juez_de_las_dos_personas(make_account, settings, db_cache, monkeypatch):
    settings.VINCULO_ENABLED = True
    acc = make_account()
    otorgar(acc, "informe_vinculo", 1, origen="compra", external_id="v:g")
    s = crear_vinculo(acc, "familia", [
        {**A, "rol": "progenitor", "genero": "neutro"}, {**B, "rol": "hijo", "genero": "masculino"},
    ])
    vistos = []
    monkeypatch.setattr(informe_service, "revisar_personas",
                        lambda texto, generos, lang, client: vistos.append((generos, lang)) or texto)
    monkeypatch.setattr(svc, "_build_client", lambda: ClienteFalso())
    es = svc.iniciar_generacion(s, "es", acc, tier="largo")
    svc.completar_generacion(es, acc)
    assert vistos == [(("neutro", "masculino"), "es")] * 8

    vistos.clear()
    pt = svc.iniciar_generacion(s, "pt", acc, tier="largo")
    svc.completar_generacion(pt, acc)
    assert vistos == [(("neutro", "masculino"), "pt")] * 8


def test_la_traduccion_del_vinculo_lleva_el_genero_de_las_dos(make_account, settings, db_cache, monkeypatch):
    from interpret.trato import instruccion_persona

    settings.VINCULO_ENABLED = True
    acc = make_account()
    otorgar(acc, "informe_vinculo", 1, origen="compra", external_id="v:t")
    s = crear_vinculo(acc, "pareja", [{**A, "genero": "femenino"}, B])
    monkeypatch.setattr(informe_service, "revisar_personas", lambda texto, *a: texto)
    cliente = ClienteFalso()
    monkeypatch.setattr(svc, "_build_client", lambda: cliente)
    es = svc.iniciar_generacion(s, "es", acc, tier="largo")
    svc.completar_generacion(es, acc)
    antes = len(cliente.llamadas)
    pt = svc.iniciar_generacion(s, "pt", acc, tier="largo")
    svc.completar_generacion(pt, acc)
    system = "\n".join(b["text"] for b in cliente.llamadas[antes]["system"])
    assert instruccion_persona("femenino", "pt", "Pessoa A") in system
    assert instruccion_persona("", "pt", "Pessoa B") in system
