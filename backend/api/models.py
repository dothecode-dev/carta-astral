import datetime as dt
import uuid
from zoneinfo import ZoneInfo

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
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


class PasarelaCheckout(models.Model):
    """Quién abrió esta sesión de pago, en qué pasarela, y para qué.

    Existe porque el webhook necesita saber a qué cuenta acreditarle la compra,
    y la metadata de la sesión no alcanza: la fila propia guarda cosas que la
    pasarela no conoce —la carta y el idioma—. La fila es la fuente de verdad;
    la metadata que viaja a Stripe es el respaldo.

    `chart` es opcional y es lo que hace que comprar desde una carta termine
    con esa carta escribiéndose, en vez de con un derecho suelto que hay que ir
    a usar a mano. `SET_NULL`: si se borra la carta antes de que llegue el
    webhook, el pago se acredita igual.
    """

    checkout_id = models.CharField(max_length=100, unique=True)
    account = models.ForeignKey(
        "Account", on_delete=models.SET_NULL, null=True, related_name="checkouts",
    )
    codigo_producto = models.CharField(max_length=50)
    chart = models.ForeignKey(
        "Chart", on_delete=models.SET_NULL, null=True, blank=True, related_name="checkouts",
    )
    # En qué idioma se compró, para escribir el informe en ése. El webhook no
    # tiene otra forma de saberlo: quien paga puede cerrar la pestaña en Polar
    # y no volver nunca, y un default silencioso le entregaría el informe pago
    # en un idioma que no eligió.
    locale = models.CharField(max_length=5, default="es")
    # Cuándo el webhook otorgó lo comprado. Lo consulta la página de retorno,
    # que existe por una carrera inevitable: el redirect del navegador es
    # instantáneo y la entrega del webhook puede llegar después.
    #
    # Se guarda acá y no se deduce mirando movimientos por fecha: dos compras
    # del mismo producto en el mismo minuto no se distinguirían así.
    acreditado_at = models.DateTimeField(null=True, blank=True)
    # El `PaymentIntent` de Stripe, que se completa al acreditar el pago.
    # `refund.created` llega con `payment_intent` y `charge`, NUNCA con el id de
    # la sesión: sin guardarlo acá, un reembolso no se puede atribuir a ninguna
    # compra. No es único a propósito: mientras el webhook no acredite queda
    # vacío en todas las filas abiertas, y un índice único las haría chocar.
    payment_intent = models.CharField(max_length=100, blank=True, default="")
    # El cupón con el que se abrió y el descuento que se esperaba, congelados
    # al abrir. El webhook valida contra ESTO, no contra lo que diga Stripe:
    # así `monto == precio - descuento` sigue comparando dos fuentes
    # independientes. Sin cupón el descuento es 0, no NULL, por lo mismo.
    cupon = models.ForeignKey(
        "Cupon", on_delete=models.SET_NULL, null=True, blank=True, related_name="checkouts",
    )
    descuento_centavos = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.checkout_id} ({self.codigo_producto})"


ZONA_CUPONES = ZoneInfo("America/Argentina/Buenos_Aires")


class Cupon(models.Model):
    """Un porcentaje de descuento sobre uno o más productos del catálogo.

    Para 1..99 % el tope de usos y el vencimiento los aplica Stripe: al crear
    el cupón se crea allá un Coupon y un Promotion Code, y los ids quedan acá.
    Como Stripe no deja editar porcentaje, tope ni vencimiento, tampoco se
    editan acá después de creado: se desactiva y se crea otro. El del 100 %
    no pasa por Stripe y sus ids quedan vacíos.

    Los cupones no se borran (`CuponUso.cupon` es PROTECT): se desactivan, y
    la constancia de quién usó cuál sobrevive.
    """

    codigo = models.CharField(
        max_length=40, unique=True,
        validators=[RegexValidator(r"^[A-Z0-9-]{3,40}$", "Sólo A-Z, 0-9 y guión, de 3 a 40")],
    )
    descripcion = models.CharField(max_length=200, blank=True, help_text="Para qué es. Uso interno.")
    porcentaje = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )
    productos = models.JSONField(default=list, help_text="Códigos del catálogo que abarca.")
    usos_maximos = models.PositiveIntegerField()
    activo = models.BooleanField(default=True)
    vence_el = models.DateField(
        null=True, blank=True, help_text="Vence a las 23:59:59 de ese día, hora de Buenos Aires.",
    )
    stripe_coupon_id = models.CharField(max_length=100, blank=True, default="")
    stripe_promotion_code_id = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(porcentaje__gte=1, porcentaje__lte=100),
                name="cupon_porcentaje_1_a_100",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} ({self.porcentaje}%)"

    @staticmethod
    def normalizar(codigo: str) -> str:
        return (codigo or "").strip().upper()

    def clean_fields(self, exclude=None):
        # Antes de validar: `promo30` y ` PROMO30 ` son el mismo cupón, y el
        # validador del campo no tiene por qué saberlo.
        self.codigo = self.normalizar(self.codigo)
        super().clean_fields(exclude=exclude)

    def clean(self):
        from django.core.exceptions import ValidationError

        from api.catalogo import CATALOGO

        if not isinstance(self.productos, list) or not self.productos:
            raise ValidationError({"productos": "Elegí al menos un producto."})
        if len(set(self.productos)) != len(self.productos):
            raise ValidationError({"productos": "Hay un producto repetido."})
        for codigo in self.productos:
            prod = CATALOGO.get(codigo)
            if prod is None:
                raise ValidationError({"productos": f"{codigo} no está en el catálogo."})
            if prod.precio_centavos <= 0:
                raise ValidationError({"productos": f"{codigo} es gratis: no admite descuento."})

    def save(self, *args, **kwargs):
        self.codigo = self.normalizar(self.codigo)
        super().save(*args, **kwargs)

    @property
    def vence_at(self) -> dt.datetime | None:
        """El instante de vencimiento en UTC, o None si no vence."""
        if self.vence_el is None:
            return None
        fin_del_dia = dt.datetime.combine(self.vence_el, dt.time(23, 59, 59), tzinfo=ZONA_CUPONES)
        return fin_del_dia.astimezone(dt.timezone.utc)

    def vencido(self, ahora: dt.datetime) -> bool:
        vence = self.vence_at
        return vence is not None and ahora > vence

    def usos_confirmados(self) -> int:
        """Cuántas veces se usó. Un uso revocado o reembolsado sigue contando:
        devolver el lugar abriría el ciclo comprar / reembolsar / repetir."""
        return self.usos.count()


class CuponUso(models.Model):
    """La constancia: quién usó qué cupón, para qué producto y cuánto pagó.

    `account` es SET_NULL: borrar la cuenta conserva el uso (degrada de «quién»
    a «cuántos», como `Movimiento`) y no devuelve el lugar. `external_id` es el
    mismo del `Movimiento` de la compra —`stripe:session:<id>`— y es único, así
    que el reintento de un webhook no cuenta dos veces.
    """

    cupon = models.ForeignKey("Cupon", on_delete=models.PROTECT, related_name="usos")
    account = models.ForeignKey(
        "Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="usos_cupon",
    )
    codigo_producto = models.CharField(max_length=40)
    descuento_centavos = models.PositiveIntegerField()
    monto_pagado_centavos = models.PositiveIntegerField()
    checkout = models.ForeignKey(
        "PasarelaCheckout", on_delete=models.SET_NULL, null=True, blank=True, related_name="usos_cupon",
    )
    external_id = models.CharField(max_length=255, unique=True)
    # Sólo para regalos del 100 %: cuándo se revocó desde el admin (RF18).
    revocado_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.cupon_id} → acc={self.account_id} ({self.codigo_producto})"
