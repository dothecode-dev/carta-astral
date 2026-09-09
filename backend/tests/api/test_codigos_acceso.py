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


def test_pedir_de_nuevo_no_invalida_el_primero():
    """Hallazgo I1 de la revisión final: regenerar la fila existente invalidaba
    el código que la persona estaba tipeando. Ahora pedir de nuevo genera un
    código NUEVO en una fila NUEVA y el primero sigue vigente — los dos sirven
    hasta que vencen (RF6 corregido)."""
    fila_1, claro_1, reenvio_1 = codigos_acceso.pedir("juan@gmail.com")
    fila_2, claro_2, reenvio_2 = codigos_acceso.pedir("juan@gmail.com")

    assert fila_1.pk != fila_2.pk
    assert claro_1 != claro_2
    assert (reenvio_1, reenvio_2) == (False, True)
    assert CodigoAcceso.objects.filter(email="juan@gmail.com").count() == 2

    # El primero sigue sirviendo.
    canjeada = codigos_acceso.canjear("juan@gmail.com", claro_1)
    assert canjeada.pk == fila_1.pk


def test_el_segundo_codigo_tambien_sirve():
    _, claro_1, _ = codigos_acceso.pedir("juan@gmail.com")
    _, claro_2, _ = codigos_acceso.pedir("juan@gmail.com")
    assert claro_1 != claro_2

    canjeada = codigos_acceso.canjear("juan@gmail.com", claro_2)
    assert canjeada.usado_en is not None


def test_canjear_con_uno_quema_los_dos():
    _, claro_1, _ = codigos_acceso.pedir("juan@gmail.com")
    _, claro_2, _ = codigos_acceso.pedir("juan@gmail.com")

    codigos_acceso.canjear("juan@gmail.com", claro_1)

    # El otro código vigente, que nunca se tipeó, ya no entra: si no, un mail
    # viejo sigue sirviendo después de que la persona ya entró.
    with pytest.raises(codigos_acceso.CodigoInvalido):
        codigos_acceso.canjear("juan@gmail.com", claro_2)


def test_cinco_intentos_repartidos_entre_dos_codigos_vigentes_queman_los_dos():
    """El techo de intentos es por DIRECCIÓN, no por fila: con dos códigos
    vigentes un atacante no puede tener 5 intentos por cada uno."""
    _, claro_1, _ = codigos_acceso.pedir("juan@gmail.com")
    _, claro_2, _ = codigos_acceso.pedir("juan@gmail.com")

    # 3 fallos contra el primero, 2 contra el segundo: 5 en total.
    for _ in range(3):
        with pytest.raises(codigos_acceso.CodigoInvalido):
            codigos_acceso.canjear("juan@gmail.com", "000000")
    for _ in range(2):
        with pytest.raises(codigos_acceso.CodigoInvalido):
            codigos_acceso.canjear("juan@gmail.com", "111111")

    # Los dos códigos correctos, ninguno tipeado todavía, fallan igual.
    with pytest.raises(codigos_acceso.CodigoInvalido):
        codigos_acceso.canjear("juan@gmail.com", claro_1)
    with pytest.raises(codigos_acceso.CodigoInvalido):
        codigos_acceso.canjear("juan@gmail.com", claro_2)


def test_un_codigo_vencido_no_sirve_aunque_haya_otro_vigente():
    fila_1, claro_1, _ = codigos_acceso.pedir("juan@gmail.com")
    _, claro_2, _ = codigos_acceso.pedir("juan@gmail.com")
    fila_1.expira_en = timezone.now() - timezone.timedelta(seconds=1)
    fila_1.save(update_fields=["expira_en"])

    with pytest.raises(codigos_acceso.CodigoInvalido):
        codigos_acceso.canjear("juan@gmail.com", claro_1)

    canjeada = codigos_acceso.canjear("juan@gmail.com", claro_2)
    assert canjeada.usado_en is not None


def test_un_codigo_vencido_sin_usar_no_bloquea_el_pedido_nuevo():
    """Ya no hay una fila única por dirección que un código vencido pudiera
    bloquear (Hallazgo I1: la constraint se sacó), pero el caso sigue siendo
    válido: pedir de nuevo después de que el anterior venció tiene que seguir
    devolviendo un código nuevo y utilizable."""
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
    """Ruling 8: el techo cuenta ENVÍOS, no filas. Ahora cada pedido —sea el
    primero o un reenvío— crea su propia fila con `envios=1`, así que el
    techo de 5 pedidos/hora sigue sosteniéndose sobre la suma, sólo que ahora
    la suma coincide con la cantidad de filas: las cinco llamadas quedan
    vigentes (nunca vencen ni se usan) y la sexta se frena."""
    for _ in range(5):
        codigos_acceso.pedir("juan@gmail.com")
    assert CodigoAcceso.objects.filter(email="juan@gmail.com").count() == 5
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


@pytest.mark.parametrize("destino", [
    "/es/carta/abc\x85",  # NEL, rango C1 (\x80-\x9f)
    "/es/carta/abc\x9f",  # límite superior del rango C1
    "/es/carta /abc",  # LINE SEPARATOR
    "/es/carta /abc",  # PARAGRAPH SEPARATOR
])
def test_un_destino_con_caracteres_de_control_unicode_tambien_se_descarta(destino):
    """El filtro original sólo cubría ASCII (\\x00-\\x1f y \\x7f): no hay forma
    conocida de explotar esto porque `destino` siempre tiene que empezar con
    "/" simple, lo que ya descarta esquemas y URLs absolutas, pero es defensa
    en profundidad barata sobre un valor que viene del cliente y termina en
    una navegación."""
    fila, _, _ = codigos_acceso.pedir("juan@gmail.com", destino=destino)
    assert fila.destino == ""
