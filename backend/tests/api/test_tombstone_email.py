import hashlib

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from api.identity import sub_hash


def test_el_hash_de_un_mail_no_es_reversible_con_una_lista_de_direcciones():
    crudo = hashlib.sha256(b"email:juan@gmail.com").hexdigest()
    assert sub_hash("email", "juan@gmail.com") != crudo


def test_google_y_apple_no_cambian():
    """Los tombstones que ya existen en producción tienen que seguir matcheando."""
    esperado = hashlib.sha256(b"google:1234567890").hexdigest()
    assert sub_hash("google", "1234567890") == esperado


@override_settings(DEBUG=False, TOMBSTONE_HMAC_KEY="")
def test_sin_clave_en_produccion_falla_ruidoso():
    """Un HMAC con clave vacía es determinístico y no protege nada. El síntoma
    de dejarlo pasar —se regalan lecturas de más— no lo nota nadie."""
    with pytest.raises(ImproperlyConfigured):
        sub_hash("email", "juan@gmail.com")
