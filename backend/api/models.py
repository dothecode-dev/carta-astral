import uuid

from django.conf import settings
from django.db import models


class BirthData(models.Model):
    name = models.CharField(max_length=200, null=True, blank=True)
    date = models.DateField()
    time = models.TimeField(null=True, blank=True)
    time_known = models.BooleanField(default=True)
    lat = models.FloatField()
    lng = models.FloatField()
    tz_name = models.CharField(max_length=64)
    datetime_utc = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Chart(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    account = models.ForeignKey(
        "Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="charts",
    )
    birth_data = models.ForeignKey(BirthData, on_delete=models.CASCADE, related_name="charts")
    house_system = models.CharField(max_length=20, default="Placidus")
    zodiac = models.CharField(max_length=20, default="Tropical")
    data = models.JSONField()
    svg = models.TextField(null=True, blank=True)
    engine_version = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)


class GeoName(models.Model):
    """Localidad de GeoNames (dataset cities500). Dato de referencia, se puebla
    con el management command import_geonames."""

    geonameid = models.IntegerField(unique=True)
    name = models.CharField(max_length=200)  # grafía local, para display
    asciiname = models.CharField(max_length=200)
    lat = models.FloatField()
    lng = models.FloatField()
    country_code = models.CharField(max_length=2)
    admin1_code = models.CharField(max_length=20, blank=True)
    admin1 = models.CharField(max_length=200, blank=True)  # nombre legible (admin1CodesASCII)
    # SOLO fallback de display si core.resolve_tz no resuelve; el cálculo
    # siempre deriva el tz de lat/lng vía el core.
    tz_geonames = models.CharField(max_length=64, blank=True)
    population = models.BigIntegerField(default=0)


class Interpretation(models.Model):
    """Interpretación LLM cacheada de una carta. Clave de cache: (chart, lang,
    prompt_version) — cambiar prompt_version genera registros nuevos."""

    chart = models.ForeignKey(Chart, on_delete=models.CASCADE, related_name="interpretations")
    account = models.ForeignKey(
        "Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="interpretations",
    )
    lang = models.CharField(max_length=2)
    prompt_version = models.CharField(max_length=20)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("chart", "lang", "prompt_version")


class CreditTransaction(models.Model):
    """Ledger append-only de créditos. Fuente de verdad financiera; el balance
    de Account se reconcilia con la suma de amount por lote."""

    KINDS = (
        ("free_grant", "free_grant"), ("purchase", "purchase"),
        ("consumption", "consumption"), ("refund", "refund"), ("adjustment", "adjustment"),
    )
    LOTS = (("free", "free"), ("paid", "paid"))
    account = models.ForeignKey(
        "Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_txns",
    )
    kind = models.CharField(max_length=20, choices=KINDS)
    lot = models.CharField(max_length=4, choices=LOTS)
    amount = models.IntegerField()  # signed: + ingresa, - consume
    interpretation = models.ForeignKey(
        Interpretation, on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_txns",
    )
    external_id = models.CharField(max_length=255, blank=True, default="")
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["external_id"],
                condition=models.Q(external_id__gt=""),
                name="uniq_credit_txn_external_id",
            ),
        ]

    def __str__(self):
        return f"{self.kind} {self.amount} (acc={self.account_id})"


class GeoNameToken(models.Model):
    """Palabra normalizada de un GeoName (incluye alias de exónimos). Permite
    búsqueda por término en vez de prefijo del nombre completo."""

    geoname = models.ForeignKey(GeoName, on_delete=models.CASCADE, related_name="tokens")
    token = models.CharField(max_length=200)

    class Meta:
        indexes = [
            models.Index(fields=["token"]),  # match exacto de token completo
            # LIKE 'x%' usa índice en Postgres; opclasses se ignora en SQLite.
            models.Index(
                name="geoname_token_prefix",
                fields=["token"],
                opclasses=["varchar_pattern_ops"],
            ),
        ]


def _default_free_balance():
    return settings.INSTALL_FREE_CREDITS


class Account(models.Model):
    """Cuenta real del usuario (identidad SSO). Sostiene créditos y cartas."""

    email = models.EmailField(blank=True, default="")
    email_verified = models.BooleanField(default=False)
    free_balance = models.PositiveIntegerField(default=_default_free_balance)
    paid_balance = models.IntegerField(default=0)  # signed: clawback de reembolso puede dejarlo negativo
    refund_count = models.PositiveIntegerField(default=0)
    flagged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False


class Device(models.Model):
    """Dispositivo vinculado a una cuenta. Para push/telemetría futura.
    No participa de auth ni de cuota."""

    account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="devices",
    )
    platform = models.CharField(max_length=20, blank=True)
    push_token = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ProviderIdentity(models.Model):
    PROVIDERS = (("apple", "apple"), ("google", "google"))
    provider = models.CharField(max_length=10, choices=PROVIDERS)
    sub = models.CharField(max_length=255)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="identities")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("provider", "sub")


class Session(models.Model):
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="sessions")
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()


class SubTombstone(models.Model):
    """Recuerda cuánto free-tier consumió una identidad SSO borrada, para que
    re-crear la cuenta no regale otra gratis. Hash anónimo, sin PII."""

    sub_hash = models.CharField(max_length=64, unique=True, db_index=True)
    free_credits_consumed = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
