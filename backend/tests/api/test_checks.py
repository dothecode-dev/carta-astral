from django.core.checks import run_checks


def test_un_producto_a_la_venta_sin_product_es_un_warning(settings, monkeypatch):
    from api import avisos

    settings.STRIPE_PRODUCTOS = {}
    monkeypatch.setenv("AVISAR_CHECKS", "1")
    avisados = []
    monkeypatch.setattr(avisos, "avisar_admin", avisados.append)

    errores = run_checks(tags=["stripe"])

    assert [e.id for e in errores] == ["api.W001"]
    assert "informe_natal" in errores[0].msg
    assert avisados and "informe_natal" in avisados[0]


def test_sin_avisar_checks_el_warning_vuelve_pero_no_se_avisa(settings, monkeypatch):
    from api import avisos

    settings.STRIPE_PRODUCTOS = {}
    monkeypatch.delenv("AVISAR_CHECKS", raising=False)
    avisados = []
    monkeypatch.setattr(avisos, "avisar_admin", avisados.append)

    errores = run_checks(tags=["stripe"])

    assert [e.id for e in errores] == ["api.W001"]
    assert avisados == []


def test_dos_codigos_con_el_mismo_product_es_un_warning(settings):
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_a", "pack_5_natal": "prod_a"}

    assert "api.W002" in [e.id for e in run_checks(tags=["stripe"])]


def test_con_todo_mapeado_no_hay_nada(settings):
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_a"}

    assert run_checks(tags=["stripe"]) == []


def test_un_product_vacio_es_un_warning(settings):
    settings.STRIPE_PRODUCTOS = {"informe_natal": ""}

    errores = run_checks(tags=["stripe"])

    assert [e.id for e in errores] == ["api.W001"]
    assert "vacío" in errores[0].msg and "informe_natal" in errores[0].msg


def test_apagado_vinculo_no_se_pide_su_product(settings):
    settings.VINCULO_ENABLED = False
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_a"}

    assert run_checks(tags=["stripe"]) == []


def test_encendido_vinculo_se_pide_su_product(settings):
    settings.VINCULO_ENABLED = True
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_a"}

    errores = run_checks(tags=["stripe"])

    assert [e.id for e in errores] == ["api.W001"]
    assert "informe_vinculo" in errores[0].msg
