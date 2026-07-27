"""Validación de id_token con firma RS256 DE VERDAD.

Hasta la auditoría del 27-jul, `_JwksValidator` estaba mockeado en el 100% de
los tests: se reemplazaba `_build_apple_validator` / `_build_google_validator`
por un fake que devolvía claims fijos. O sea que **nada** verificaba que la
firma se comprueba, ni que se rechacen `aud`/`iss` ajenos o tokens vencidos.

Y sobre todo: el `nonce` —el anti-replay del login— no tenía cobertura alguna.
Sin esa verificación, un id_token interceptado se puede reusar.

Acá se firman tokens reales con una clave RSA generada al vuelo y se sirve un
JWKS falso, sin red: el validador corre completo, igual que en producción.
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from api import sso

AUD = "com.cartaastral.app"
ISS = "https://appleid.apple.com"
KID = "test-key-1"


@pytest.fixture(scope="module")
def clave():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def validador(clave, monkeypatch):
    """El validador real, con el lookup de JWKS apuntando a nuestra clave.

    Se reemplaza SÓLO la obtención de la clave (la parte que va por red), no la
    verificación: firma, iss, aud, exp y nonce se comprueban de verdad.
    """
    v = sso._JwksValidator(jwks_url="https://ejemplo/jwks", issuer=ISS, audience=AUD)
    monkeypatch.setattr(v, "_signing_key", lambda _t: type("K", (), {"key": clave.public_key()})())
    return v


def _token(clave, **over):
    ahora = int(time.time())
    claims = {
        "iss": ISS,
        "aud": AUD,
        "sub": "APPLE_SUB_123",
        "email": "u@x.com",
        "email_verified": "true",
        "iat": ahora,
        "exp": ahora + 600,
    }
    claims.update(over)
    return jwt.encode(claims, clave, algorithm="RS256", headers={"kid": KID})


def test_un_token_bien_firmado_se_acepta(validador, clave):
    claims = validador(_token(clave))

    assert claims["sub"] == "APPLE_SUB_123"


def test_un_token_firmado_con_OTRA_clave_se_rechaza(validador):
    """El corazón del asunto: sin esto, cualquiera se loguea como cualquiera."""
    impostora = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with pytest.raises(sso.SSOError):
        validador(_token(impostora))


def test_un_token_para_otra_app_se_rechaza(validador, clave):
    """`aud` ajeno = token emitido para otra aplicación."""
    with pytest.raises(sso.SSOError):
        validador(_token(clave, aud="com.otra.app"))


def test_un_token_de_otro_emisor_se_rechaza(validador, clave):
    with pytest.raises(sso.SSOError):
        validador(_token(clave, iss="https://impostor.example"))


def test_un_token_vencido_se_rechaza(validador, clave):
    ahora = int(time.time())
    with pytest.raises(sso.SSOError):
        validador(_token(clave, iat=ahora - 7200, exp=ahora - 3600))


def test_el_nonce_que_no_coincide_se_rechaza(validador, clave):
    """ANTI-REPLAY. Sin cobertura hasta hoy.

    La app manda un nonce por login; si el backend no lo compara, un id_token
    interceptado sirve para entrar de nuevo.
    """
    token = _token(clave, nonce="el-de-esta-sesion")

    with pytest.raises(sso.SSOError):
        validador(token, nonce="otro-distinto")


def test_el_nonce_correcto_pasa(validador, clave):
    claims = validador(_token(clave, nonce="abc123"), nonce="abc123")

    assert claims["nonce"] == "abc123"


def test_si_el_token_no_trae_nonce_pero_se_esperaba_uno_se_rechaza(validador, clave):
    with pytest.raises(sso.SSOError):
        validador(_token(clave), nonce="se-esperaba-este")


def test_si_falla_el_lookup_de_la_clave_sale_error_tipado(clave, monkeypatch):
    """JWKS caído o `kid` rotado: tiene que salir SSOError, no un error crudo
    que termine en un 500.

    Se rompe el cliente JWKS (la capa de red), NO `_signing_key`: es justamente
    ese método el que traduce el fallo a SSOError, así que mockearlo saltearía
    lo que se quiere probar.
    """
    v = sso._JwksValidator(jwks_url="https://ejemplo/jwks", issuer=ISS, audience=AUD)

    class ClienteRoto:
        def __init__(self, *a, **kw):
            pass

        def get_signing_key_from_jwt(self, _t):
            raise RuntimeError("jwks no responde")

    monkeypatch.setattr(sso.jwt, "PyJWKClient", ClienteRoto)

    with pytest.raises(sso.SSOError):
        v(_token(clave))


@pytest.mark.parametrize(
    "valor,esperado",
    [
        (True, True), ("true", True), ("True", True), (1, True), ("1", True),
        (False, False), ("false", False), (0, False), (None, False), ("", False),
        ("cualquier-cosa", False),
    ],
)
def test_email_verified_solo_es_verdadero_con_valores_explicitos(valor, esperado):
    """Este flag decide si una identidad SSO se LINKEA a una cuenta existente
    por email. Si algo raro colara como verdadero, sería un takeover de cuenta.
    """
    assert sso._coerce_verified(valor) is esperado
