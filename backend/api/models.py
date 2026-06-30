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
    lang = models.CharField(max_length=2)
    prompt_version = models.CharField(max_length=20)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("chart", "lang", "prompt_version")


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


class Installation(models.Model):
    """Identidad anónima por instalación de la app. El token se guarda hasheado."""

    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    purchased_credits = models.PositiveIntegerField(default=0)
    platform = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # para DRF: la instalación actúa como "actor" autenticado
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False
