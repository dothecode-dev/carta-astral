import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_la_cuenta_expone_sus_derechos_y_no_saldos(make_account):
    """`/api/account/` deja de hablar de saldos y pasa a exponer derechos por
    producto (Task 12): con dos contadores era imposible distinguir un pack
    de 5 informes natales de una lectura breve, y la web necesita esa
    distinción para decidir qué ofrecer.

    El contrato se afirma por el set COMPLETO de claves, no listando las que
    ya no están: así, cualquier saldo suelto que alguien reintroduzca en el
    serializer rompe este test, se llame como se llame."""
    from api.auth import create_session
    from api.canje import otorgar

    acc = make_account()
    otorgar(acc, "informe_natal", 1, origen="compra", external_id="p:1")
    token = create_session(acc)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    data = c.get("/api/account/").json()

    assert data["account_id"] == acc.id
    assert data["deuda"] == 0
    assert {
        "codigo_producto": "informe_natal", "cantidad_restante": 1, "vigente_hasta": None,
    } in data["derechos"]
    # `email` se sumó el 03-09-2026: la pantalla de cuenta no podía decir
    # con qué mail estabas adentro.
    assert set(data) == {"account_id", "deuda", "derechos", "email"}
