import uuid

from django.db import models

from interpret.prompts import TIER_CORTO, TIER_LARGO


class BirthData(models.Model):
    name = models.CharField(max_length=200, null=True, blank=True)
    # Etiqueta legible del lugar tal como la eligió el usuario en el geocoder
    # ("Florida, Buenos Aires, AR"). Solo display; el cálculo usa lat/lng.
    place_label = models.CharField(max_length=200, blank=True, default="")
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
    prompt_version, tier) — cambiar prompt_version genera registros nuevos."""

    # Mismos literales que interpret.prompts.SECCION_BREVE/SECCIONES usan para
    # elegir el catálogo (`secciones_aplicables`): dos fuentes de verdad sin
    # atar dejarían el bug en silencio si alguien cambia una y no la otra.
    TIERS = ((TIER_CORTO, TIER_CORTO), (TIER_LARGO, TIER_LARGO))

    chart = models.ForeignKey(Chart, on_delete=models.CASCADE, related_name="interpretations")
    account = models.ForeignKey(
        "Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="interpretations",
    )
    lang = models.CharField(max_length=2)
    prompt_version = models.CharField(max_length=20)
    # Qué producto es este texto: la lectura breve que compra un crédito free
    # o el informe de ocho secciones que compra un crédito pago. Está en la
    # clave única porque los dos conviven sobre la misma carta (RF6): quien
    # leyó la breve y después paga tiene que poder generar el completo sin
    # perder la breve.
    tier = models.CharField(max_length=6, choices=TIERS, default=TIER_LARGO)
    text = models.TextField()
    # sha256 del input del LLM (chart.data canónico + lang + prompt_version).
    # Permite reutilizar el texto entre cartas idénticas sin llamar a la API.
    content_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Un informe se arma de a secciones: hasta que están las ocho, no se
    # entrega ni se considera pago.
    completa = models.BooleanField(default=False)

    # Cuántas veces `completar_generacion` intentó terminar este informe
    # (Task 10, RF21). Agotados `INTENTOS_MAXIMOS` sin completarlo, la
    # política es devolver el crédito y borrar la fila: no se entrega un
    # informe a medias por lo que costó el completo.
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("chart", "lang", "prompt_version", "tier")


class InterpretationSection(models.Model):
    """Una sección del informe, persistida apenas se termina de generar.

    Es lo que hace la generación reanudable sin cola de trabajos: si el proceso
    muere a mitad, las secciones ya escritas siguen ahí y el reintento sigue
    desde la que falta, sin volver a pagarle al modelo ni al usuario."""

    interpretation = models.ForeignKey(
        Interpretation, on_delete=models.CASCADE, related_name="secciones",
    )
    slug = models.CharField(max_length=20)
    orden = models.PositiveSmallIntegerField()
    texto = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["orden"]
        unique_together = ("interpretation", "slug")

    def __str__(self):
        return f"{self.slug} (interp={self.interpretation_id})"


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


class Account(models.Model):
    """Cuenta real del usuario (identidad SSO). Sostiene derechos y cartas.

    Lo que la cuenta puede hacer NO vive acá: vive en `Derecho` (uno por
    producto) y su historia en `Movimiento`. Los dos contadores sueltos del
    modelo de cobro viejo los borró la `0025`.
    """

    email = models.EmailField(blank=True, default="")
    email_verified = models.BooleanField(default=False)
    refund_count = models.PositiveIntegerField(default=0)
    # Lo que la cuenta debe tras un reembolso de algo que ya consumió. Vive
    # separada del saldo a propósito: saldo es lo que se puede gastar, deuda es
    # lo que se debe, y meterlos en la misma columna hacía imposible exigir que
    # el saldo no fuera negativo.
    deuda = models.PositiveIntegerField(default=0)
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
    # Sólo Apple: refresh_token del server API, necesario para revocar en el
    # borrado de cuenta (guideline 5.1.1(v)). Inútil sin el client_secret, que
    # se firma con la key .p8 que vive en env, no en la DB.
    refresh_token = models.TextField(blank=True, default="")

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


class Derecho(models.Model):
    """Lo que una cuenta puede usar. Consumible: cantidad. Acceso: vigencia."""

    account = models.ForeignKey("Account", on_delete=models.CASCADE, related_name="derechos")
    codigo_producto = models.CharField(max_length=40)
    cantidad_restante = models.PositiveIntegerField(null=True, blank=True)
    vigente_hasta = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "codigo_producto"], name="uniq_derecho_cuenta_producto",
            ),
            # Un derecho es de una naturaleza o de la otra, nunca de las dos.
            models.CheckConstraint(
                condition=(
                    models.Q(cantidad_restante__isnull=False, vigente_hasta__isnull=True)
                    | models.Q(cantidad_restante__isnull=True, vigente_hasta__isnull=False)
                ),
                name="derecho_es_consumible_o_acceso",
            ),
        ]

    def __str__(self):
        return f"{self.codigo_producto} (acc={self.account_id})"


class Movimiento(models.Model):
    """Registro append-only de todo cambio de derechos o de deuda.

    Es el rastro de auditoría de CADA operación (qué se compró, canjeó,
    devolvió o revocó), no una contabilidad que sume sola al saldo exacto de
    un `Derecho`. Dos caminos rompen esa suma directa, los dos correctos en
    unidades:

    - un pack registra el movimiento con el producto COMPRADO
      (`pack_5_natal`, cantidad 1), pero acredita el derecho del producto que
      `Producto.otorga` traduce (`informe_natal`, +5): sumando sólo los
      movimientos de `informe_natal` faltan esas 5 unidades, que están en el
      movimiento de `pack_5_natal`.
    - `otorgar` cancela deuda antes de acreditar saldo, y esa cancelación no
      deja movimiento propio: con deuda 3 y una compra de 5, el movimiento
      dice +5 pero el derecho sube sólo 2.

    Para reconstruir el saldo exacto de un producto hay que sumar sus
    movimientos, traducir los de cualquier producto que lo `otorga`, y
    restar lo que `otorgar` haya aplicado a deuda en el camino.
    """

    TIPOS = (
        ("otorgamiento", "otorgamiento"), ("consumo", "consumo"),
        ("devolucion", "devolucion"), ("revocacion", "revocacion"),
    )
    ORIGENES = (
        ("compra", "compra"), ("regalo", "regalo"), ("cupon", "cupon"), ("ajuste", "ajuste"),
    )

    account = models.ForeignKey(
        "Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="movimientos",
    )
    codigo_producto = models.CharField(max_length=40)
    tipo = models.CharField(max_length=12, choices=TIPOS)
    origen = models.CharField(max_length=8, choices=ORIGENES)
    cantidad = models.IntegerField(help_text="firmado: + ingresa, - consume")
    chart = models.ForeignKey(
        "Chart", on_delete=models.SET_NULL, null=True, blank=True, related_name="movimientos",
    )
    external_id = models.CharField(max_length=255, blank=True, default="")
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            # Misma idempotencia que ya sostiene el webhook de pagos hoy: el
            # índice es parcial porque los movimientos sin origen externo
            # (consumos) no tienen id que compartir.
            models.UniqueConstraint(
                fields=["external_id"], condition=models.Q(external_id__gt=""),
                name="uniq_movimiento_external_id",
            ),
        ]

    def __str__(self):
        return f"{self.tipo} {self.cantidad} (acc={self.account_id})"


class PolarCheckout(models.Model):
    """Quién abrió esta sesión de pago, y para qué.

    Existe porque el webhook necesita saber a qué cuenta acreditarle la orden, y
    la propagación de `metadata` del checkout a la orden **no está en el
    contrato publicado** de Polar: se confirmó leyendo su fuente, que puede
    cambiar sin aviso. `order.checkout_id` sí está garantizado, así que la
    relación se guarda de este lado y la metadata queda como respaldo.

    `chart` es opcional y es lo que hace que comprar desde una carta termine
    con esa carta escribiéndose, en vez de con un derecho suelto que hay que ir
    a usar a mano. `SET_NULL`: si se borra la carta antes de que llegue el
    webhook, el pago se acredita igual.
    """

    checkout_id = models.CharField(max_length=100, unique=True)
    account = models.ForeignKey(
        "Account", on_delete=models.SET_NULL, null=True, related_name="checkouts_polar",
    )
    codigo_producto = models.CharField(max_length=50)
    chart = models.ForeignKey(
        "Chart", on_delete=models.SET_NULL, null=True, blank=True, related_name="checkouts_polar",
    )
    # En qué idioma se compró, para escribir el informe en ése. El webhook no
    # tiene otra forma de saberlo: quien paga puede cerrar la pestaña en Polar
    # y no volver nunca, y un default silencioso le entregaría el informe pago
    # en un idioma que no eligió.
    locale = models.CharField(max_length=5, default="es")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.checkout_id} ({self.codigo_producto})"
