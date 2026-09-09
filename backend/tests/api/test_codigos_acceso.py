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


@override_settings(CODIGO_PEDIDOS_HORA=5)
def test_el_reenvio_consume_el_mismo_techo_que_un_pedido_nuevo(django_cache_cleared):
    """Ruling 8: un reenvío no crea fila, pero manda un mail igual. Contar
    FILAS creadas (como hacía la versión anterior) dejaba pedir códigos en
    loop contra una dirección ajena sin tocar el techo — la tabla de riesgos
    de la spec lo lista como Importante. Acá el código sigue vigente en las
    cinco llamadas (nunca vence ni se usa), así que las 4 últimas son
    reenvíos sobre la misma fila."""
    for _ in range(5):
        codigos_acceso.pedir("juan@gmail.com")
    assert CodigoAcceso.objects.filter(email="juan@gmail.com").count() == 1
    with pytest.raises(codigos_acceso.DemasiadosPedidos):
        codigos_acceso.pedir("juan@gmail.com")


def test_el_destino_viaja_en_la_fila():
    """En iOS la persona sale a Mail y vuelve, a veces por una pestaña nueva:
    ahí el `next` de la URL ya no existe."""
    _, claro, _ = codigos_acceso.pedir("juan@gmail.com", destino="/es/carta/abc")
    fila = codigos_acceso.canjear("juan@gmail.com", claro)
    assert fila.destino == "/es/carta/abc"


def test_el_reenvio_actualiza_el_destino_si_viene_uno_nuevo():
    """Ruling 10: RF16 existe porque la persona vuelve a la página equivocada
    después de entrar. Que un reenvío mande al destino viejo es el mismo bug
    que el requisito vino a cerrar."""
    codigos_acceso.pedir("juan@gmail.com", destino="/es/carta/vieja")
    fila, claro, reenvio = codigos_acceso.pedir("juan@gmail.com", destino="/es/carta/nueva")
    assert reenvio is True
    assert fila.destino == "/es/carta/nueva"
    canjeada = codigos_acceso.canjear("juan@gmail.com", claro)
    assert canjeada.destino == "/es/carta/nueva"


def test_el_reenvio_conserva_el_destino_si_no_viene_uno_nuevo():
    codigos_acceso.pedir("juan@gmail.com", destino="/es/carta/vieja")
    fila, _, reenvio = codigos_acceso.pedir("juan@gmail.com")
    assert reenvio is True
    assert fila.destino == "/es/carta/vieja"


# --- Ruling 16: `destino` sólo vale como path interno -----------------------
#
# `destino` lo manda quien llama sin pasar por ninguna autenticación, y la web
# lo usa para redirigir después de loguear: sin validar, es un open redirect
# post-autenticación. Se descarta en silencio —el login sigue andando— en vez
# de rechazar el pedido.


@pytest.mark.parametrize("destino", [
    "https://malo.example",
    "//malo.example",
    "/\\malo",
])
def test_un_destino_que_no_es_un_path_interno_se_descarta_sin_rechazar_el_pedido(destino):
    fila, claro, _ = codigos_acceso.pedir("juan@gmail.com", destino=destino)
    assert fila.destino == ""
    assert len(claro) == 6 and claro.isdigit()


def test_un_path_interno_valido_se_guarda_tal_cual():
    fila, _, _ = codigos_acceso.pedir("juan@gmail.com", destino="/es/carta/abc")
    assert fila.destino == "/es/carta/abc"


def test_un_destino_demasiado_largo_se_descarta():
    fila, _, _ = codigos_acceso.pedir("juan@gmail.com", destino="/" + "a" * 200)
    assert fila.destino == ""


def test_un_destino_con_caracteres_de_control_se_descarta():
    fila, _, _ = codigos_acceso.pedir("juan@gmail.com", destino="/es/carta\n/abc")
    assert fila.destino == ""
