import pytest
from django.test import override_settings
from django.utils import timezone

from api import codigos_acceso
from api.models import CodigoAcceso

pytestmark = pytest.mark.django_db


def test_normaliza_minusculas_y_espacios():
    assert codigos_acceso.normalizar("  Juan@Gmail.com ") == "juan@gmail.com"


def test_el_codigo_no_se_guarda_en_claro():
    _, claro, _ = codigos_acceso.pedir("juan@gmail.com")
    assert len(claro) == 6 and claro.isdigit()
    assert not CodigoAcceso.objects.filter(codigo_hash=claro).exists()


def test_pedir_de_nuevo_reenvia_la_misma_fila():
    """Regenerarlo abría una denegación de acceso: quien supiera tu dirección
    podía pedir códigos en loop y matar el que estabas tipeando.

    El código en claro no se guarda nunca, así que un reenvío no puede releer
    el primero: lo que se afirma es que la FILA es la misma (Ruling 4), no que
    el string coincida — eso es imposible por diseño."""
    fila_1, _, reenvio_1 = codigos_acceso.pedir("juan@gmail.com")
    fila_2, _, reenvio_2 = codigos_acceso.pedir("juan@gmail.com")
    assert fila_1.pk == fila_2.pk
    assert fila_1.intentos == fila_2.intentos
    assert (reenvio_1, reenvio_2) == (False, True)
    assert CodigoAcceso.objects.filter(email="juan@gmail.com").count() == 1


def test_un_codigo_vencido_sin_usar_no_bloquea_el_pedido_nuevo():
    """Ruling 3: la constraint parcial sólo mira `usado_en IS NULL`, así que un
    código vencido y sin usar sigue ocupando la fila única. `pedir()` tiene que
    descartarlo antes de crear uno nuevo, o el segundo pedido revienta con
    IntegrityError."""
    fila, _, _ = codigos_acceso.pedir("juan@gmail.com")
    fila.expira_en = timezone.now() - timezone.timedelta(seconds=1)
    fila.save(update_fields=["expira_en"])

    fila_nueva, claro_nuevo, reenvio = codigos_acceso.pedir("juan@gmail.com")

    assert reenvio is False
    assert fila_nueva.pk != fila.pk
    assert len(claro_nuevo) == 6 and claro_nuevo.isdigit()


def test_cinco_intentos_fallidos_lo_queman():
    _, claro, _ = codigos_acceso.pedir("juan@gmail.com")
    for _ in range(5):
        with pytest.raises(codigos_acceso.CodigoInvalido):
            codigos_acceso.canjear("juan@gmail.com", "000000")
    # el sexto trae el código CORRECTO y tiene que fallar igual
    with pytest.raises(codigos_acceso.CodigoInvalido):
        codigos_acceso.canjear("juan@gmail.com", claro)


def test_un_codigo_vencido_no_sirve():
    fila, claro, _ = codigos_acceso.pedir("juan@gmail.com")
    fila.expira_en = timezone.now() - timezone.timedelta(seconds=1)
    fila.save(update_fields=["expira_en"])
    with pytest.raises(codigos_acceso.CodigoInvalido):
        codigos_acceso.canjear("juan@gmail.com", claro)


def test_un_codigo_ya_usado_no_sirve_dos_veces():
    _, claro, _ = codigos_acceso.pedir("juan@gmail.com")
    codigos_acceso.canjear("juan@gmail.com", claro)
    with pytest.raises(codigos_acceso.CodigoInvalido):
        codigos_acceso.canjear("juan@gmail.com", claro)


@override_settings(CODIGO_PEDIDOS_HORA=5)
def test_el_techo_por_direccion_se_cuenta_en_la_tabla(django_cache_cleared):
    """En la tabla y no en el caché: el caché se desaloja y ahí el techo
    desaparece sin que nadie se entere."""
    for _ in range(5):
        fila, _, _ = codigos_acceso.pedir("juan@gmail.com")
        fila.usado_en = timezone.now()
        fila.save(update_fields=["usado_en"])
    with pytest.raises(codigos_acceso.DemasiadosPedidos):
        codigos_acceso.pedir("juan@gmail.com")


def test_el_destino_viaja_en_la_fila():
    """En iOS la persona sale a Mail y vuelve, a veces por una pestaña nueva:
    ahí el `next` de la URL ya no existe."""
    _, claro, _ = codigos_acceso.pedir("juan@gmail.com", destino="/es/carta/abc")
    fila = codigos_acceso.canjear("juan@gmail.com", claro)
    assert fila.destino == "/es/carta/abc"
