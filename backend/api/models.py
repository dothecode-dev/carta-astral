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
    # Trato del lector (spec 2026-10-07-trato-lector). "" = no eligió → neutro.
    trato = models.CharField(max_length=10, blank=True, default="")


class _CartasDeLista(models.Manager):
    """Las cartas que la persona ve y usa como cartas. Las copias de un
    vínculo (`en_lista=False`, RF15) no existen para ningún camino de carta
    (RF12): es el manager por defecto, así que `get_object_or_404(Chart, …)`,
    `account.charts` y el admin las excluyen sin acordarse. Quien necesita
    todas —el vínculo, el borrado de cuenta, la purga— usa `Chart.todas`."""

    def get_queryset(self):
        return super().get_queryset().filter(en_lista=True)


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
    # RF12/RF15: False en las copias de un vínculo. `db_default` y no sólo
    # `default`: durante el deploy el contenedor anterior crea cartas sin
    # conocer la columna, y sin valor en la base cada INSERT fallaría.
    en_lista = models.BooleanField(default=True, db_default=True)

    objects = _CartasDeLista()
    todas = models.Manager()


class Sujeto(models.Model):
    """De qué es un informe pago: hoy una carta (natal); con Vínculo, un par.

    Parte 2 de la spec de Vínculo (RF5). El natal es un sujeto con UNA carta,
    `natal_de`, y hay uno solo por carta: lo garantiza la base (OneToOne), no la
    disciplina del código, porque dos sujetos natales para la misma carta
    romperían la idempotencia del cobro —el mismo informe se podría canjear
    una vez por cada sujeto—. Las cartas de un vínculo llegan en la parte 3.
    """

    NATAL = "natal"
    VINCULO = "vinculo"
    PRODUCTOS = ((NATAL, NATAL), (VINCULO, VINCULO))

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    account = models.ForeignKey(
        "Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="sujetos",
    )
    producto = models.CharField(max_length=20, choices=PRODUCTOS)
    natal_de = models.OneToOneField(
        Chart, on_delete=models.CASCADE, null=True, blank=True, related_name="sujeto_natal",
    )
    parametros = models.JSONField(default=dict, blank=True)
    data = models.JSONField(default=dict, blank=True)
    engine_version = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Un natal tiene carta, y sólo un natal la tiene en `natal_de`.
            models.CheckConstraint(
                condition=(
                    models.Q(producto="natal", natal_de__isnull=False)
                    | (~models.Q(producto="natal") & models.Q(natal_de__isnull=True))
                ),
                name="sujeto_natal_tiene_carta_y_solo_el",
            ),
        ]

    def __str__(self):
        return f"{self.producto} {self.uuid}"


class SujetoCarta(models.Model):
    """Las cartas de un sujeto que no es natal (RF5): para un vínculo, dos
    copias con su orden (A=0, B=1) y el rol de cada persona (RF13). El natal
    no la usa: su carta está en `Sujeto.natal_de`."""

    sujeto = models.ForeignKey(Sujeto, on_delete=models.CASCADE, related_name="cartas")
    carta = models.ForeignKey(Chart, on_delete=models.CASCADE, related_name="en_sujetos")
    orden = models.PositiveSmallIntegerField()
    rol = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        ordering = ["orden"]
        constraints = [
            models.UniqueConstraint(fields=["sujeto", "orden"], name="sujeto_carta_orden_unico"),
        ]


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
    """Interpretación LLM cacheada de un sujeto. Clave de cache: (sujeto, lang,
    prompt_version, tier) — cambiar prompt_version genera registros nuevos."""

    # Mismos literales que interpret.prompts.SECCION_BREVE/SECCIONES usan para
    # elegir el catálogo (`secciones_aplicables`): dos fuentes de verdad sin
    # atar dejarían el bug en silencio si alguien cambia una y no la otra.
    TIERS = ((TIER_CORTO, TIER_CORTO), (TIER_LARGO, TIER_LARGO))

    sujeto = models.ForeignKey("Sujeto", on_delete=models.CASCADE, related_name="interpretations")
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
    # Trato del lector (spec 2026-10-07-trato-lector). "" = no eligió → neutro.
    # Copia del de la carta al crear el informe: lo usan todas sus secciones,
    # el cron y sus traducciones, aunque la persona lo cambie después (RF5).
    trato = models.CharField(max_length=10, blank=True, default="")
    # De qué informe es traducción este (nulo = se escribió de cero). Es lo que
    # permite distinguir, al retomar, una traducción a medias del mismo origen
    # (se completa lo que falta) de secciones escritas de cero (se descartan y
    # se traduce todo: mezclarlas deja contenido y trato inconsistentes).
    traducido_de = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="traducciones",
    )
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
    # Cuándo salió el mail de «tu informe está listo». Marcarlo con un UPDATE
    # condicional es lo que hace que el hilo y el cron no avisen dos veces.
    avisada_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sujeto", "lang", "prompt_version", "tier"],
                name="uniq_interpretacion_por_sujeto",
            ),
        ]


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
    PROVIDERS = (("apple", "apple"), ("google", "google"), ("email", "email"))
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


class CodigoAcceso(models.Model):
    """El código de 6 dígitos que abre la puerta de mail.

    Vive en tabla y no en el caché de la base a propósito: el caché se desaloja
    y ahí se pierde el login a mitad de camino, y el contador de intentos
    necesita el bloqueo de fila que da Postgres.

    El código NUNCA se guarda en claro: sólo su sha256. Igual que `Session`.
    """

    email = models.EmailField()
    codigo_hash = models.CharField(max_length=64)
    # A dónde volver al entrar. Viaja acá además de en la URL porque en iOS la
    # persona sale a Mail y vuelve, a veces por una pestaña nueva, y ahí el
    # `next` de la URL ya no existe (RF16).
    destino = models.CharField(max_length=200, blank=True, default="")
    intentos = models.PositiveSmallIntegerField(default=0)
    # Cuántos mails salieron por esta fila: 1 al crearla, +1 por cada reenvío.
    # El techo de RF9 («5 pedidos/hora») cuenta la SUMA de este campo sobre las
    # filas de la dirección en la última hora, no `count()` de filas — un
    # reenvío no crea fila nueva, así que contar filas dejaba pedir en loop
    # contra una dirección ajena sin tocar el techo (Ruling 8, T5 fix round 1).
    envios = models.PositiveSmallIntegerField(default=1)
    usado_en = models.DateTimeField(null=True, blank=True)
    expira_en = models.DateTimeField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["email", "creado_en"])]
        # Hallazgo I1 de la revisión final: hasta acá había una
        # UniqueConstraint parcial sobre (email) con usado_en IS NULL — un
        # solo código vigente por dirección. Eso es lo que hacía que pedir un
        # código nuevo mientras había uno vigente tuviera que REENVIAR la
        # misma fila (re-hasheándola) en vez de crear una nueva: si no, el
        # segundo `create()` chocaba con la constraint. Y ese reenvío
        # invalidaba el código que la persona estaba tipeando, exactamente lo
        # que RF6 pedía evitar.
        #
        # La constraint se saca a propósito: ahora pueden convivir varios
        # códigos vigentes por dirección, cada `pedir()` crea una fila nueva y
        # ninguna se toca. El techo de intentos (RF9) pasa a sostenerse en
        # `canjear()` sumando `intentos` de todas las filas vigentes de la
        # dirección, no en esta constraint.


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
    # Parte 2 de Vínculo: lo escribe `canje.py`, explícito (sin `save()` mágico).
    sujeto = models.ForeignKey(
        "Sujeto", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="movimientos",
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

    `sujeto` es opcional y es lo que hace que comprar desde una carta termine
    con ese informe escribiéndose, en vez de con un derecho suelto que hay que
    ir a usar a mano. `SET_NULL`: si se borra la carta (y con ella su sujeto)
    antes de que llegue el webhook, el pago se acredita igual.
    """

    STRIPE = "stripe"
    MERCADOPAGO = "mercadopago"
    PASARELAS = [(STRIPE, "stripe"), (MERCADOPAGO, "mercadopago")]

    # Por qué pasarela se cobró. Sin default a propósito: quien crea la fila
    # tiene que decirlo, y una fila sin pasarela la rechaza el CheckConstraint.
    pasarela = models.CharField(max_length=12, choices=PASARELAS)
    # La preferencia de Mercado Pago con la que se abrió el pago. El id del
    # pago de MP se guarda en `pago_id`, no en otra columna.
    mp_preferencia_id = models.CharField(max_length=100, blank=True, default="")
    # El mail de quien compra sin cuenta, el que pide NUESTRO formulario antes
    # de abrir el pago (RF8b) —no el que informe la pasarela—: con ése se
    # adjudica la compra a una cuenta.
    mail_comprador = models.EmailField(blank=True, default="")
    checkout_id = models.CharField(max_length=100, unique=True)
    account = models.ForeignKey(
        "Account", on_delete=models.SET_NULL, null=True, related_name="checkouts",
    )
    codigo_producto = models.CharField(max_length=50)
    sujeto = models.ForeignKey(
        "Sujeto", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="checkouts",
    )
    # En qué idioma se compró, para escribir el informe en ése. El webhook no
    # tiene otra forma de saberlo: quien paga puede cerrar la pestaña de la pasarela
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
    # El id del pago en la pasarela (en Stripe el `PaymentIntent`), que se completa al acreditar el pago.
    # `refund.created` llega con `payment_intent` y `charge`, NUNCA con el id de
    # la sesión: sin guardarlo acá, un reembolso no se puede atribuir a ninguna
    # compra. No es único a propósito: mientras el webhook no acredite queda
    # vacío en todas las filas abiertas, y un índice único las haría chocar.
    #
    # La columna sigue llamándose `payment_intent` A PROPÓSITO (`db_column`):
    # el rename de la 0064 es sólo de estado. Durante un deploy el contenedor
    # nuevo corre `migrate` mientras el viejo sigue atendiendo, y si el deploy
    # falla el código viejo queda contra la base migrada: renombrar la columna
    # hacía que todo camino de cobro del código viejo diera 500.
    pago_id = models.CharField(max_length=100, blank=True, default="", db_column="payment_intent")
    # El cupón con el que se abrió y el descuento que se esperaba, congelados
    # al abrir. El webhook valida contra ESTO, no contra lo que diga Stripe:
    # así `monto == precio - descuento` sigue comparando dos fuentes
    # independientes. Sin cupón el descuento es 0, no NULL, por lo mismo.
    cupon = models.ForeignKey(
        "Cupon", on_delete=models.SET_NULL, null=True, blank=True, related_name="checkouts",
    )
    descuento_centavos = models.PositiveIntegerField(default=0)
    # El precio de lista con el que se abrió la sesión, congelado igual que el
    # descuento. Stripe cobra ESE precio durante la hora que vive la sesión,
    # aunque el catálogo cambie en el medio: validar contra el catálogo de ese
    # momento le cobraría a alguien sin darle nada. Nulo en las filas
    # anteriores a este campo, que siguen validando contra el catálogo.
    precio_centavos = models.PositiveIntegerField(null=True, blank=True)
    # En qué moneda se abrió (ISO 4217 en minúscula, como la manda Stripe en
    # `currency`). `precio_centavos`, `descuento_centavos` y
    # `reembolsado_centavos` están en ESTA moneda. El webhook exige que la
    # sesión venga en la misma: un monto sin su moneda no se puede comparar
    # con nada (spec cobro-brl-pix, RF9/RF11).
    moneda = models.CharField(max_length=3, default="usd")
    # Cuánto devolvió Stripe de esta compra, sumando reembolsos. Es lo que
    # deja que la pantalla de cuenta diga «reembolsada» sin sumar movimientos.
    reembolsado_centavos = models.PositiveIntegerField(default=0)
    # Cuántas unidades de lo que la compra otorgó se revocaron (reembolsos y
    # disputas). Se guarda y no se deduce del monto: ver `api/devoluciones.py`.
    unidades_revocadas = models.PositiveIntegerField(default=0)
    # La URL de la sesión de Stripe. Mientras la sesión sigue abierta es lo
    # que deja retomar un pago a medias desde la cuenta; después no sirve.
    # Vacía en las filas anteriores a este campo. Las URLs de Checkout pasan
    # largo los 255 caracteres.
    url = models.CharField(max_length=2000, blank=True, default="")
    # Cuándo Stripe avisó que la sesión venció sin pagarse
    # (`checkout.session.expired`). Una fila vencida no es una compra ni un
    # pago en curso, y deja de listarse. Nunca convive con `acreditado_at`:
    # una sesión pagada no vence, y si el evento llegara igual la plata manda.
    vencido_at = models.DateTimeField(null=True, blank=True)
    # Sólo Mercado Pago: cuándo el cron `vencer_checkouts` revisó la fila por
    # última vez y la dio por cerrada —sin pagos esperando; acreditada,
    # vencida o con un pago que no se pudo acreditar y ya se avisó—. Una fila
    # revisada no se vuelve a buscar en MP (Ruling 12 del plan fase 1).
    mp_revisado_at = models.DateTimeField(null=True, blank=True)
    # Sólo el camino de `cobro` (hoy Mercado Pago): cuándo `arrancar_informe`
    # volvió sin excepción tras acreditar —con informe o sin nada que
    # arrancar—. Una notificación posterior del MISMO pago no vuelve a
    # arrancarlo: el informe pudo rendirse (se borra y el derecho se devuelve)
    # y re-arrancarlo lo cobraría de nuevo. Mientras esté vacía, la repetición
    # reintenta el arranque (code review A, plan fase 1).
    informe_arrancado_at = models.DateTimeField(null=True, blank=True)
    # «Pagar es entrar» (spec 2026-10-07): checkout abierto sin cuenta. La
    # cuenta la pone el webhook por el mail del pago; `cuenta_nueva` dice si la
    # creó esta compra (sólo entonces se puede canjear por sesión); el nonce
    # ata el canje al navegador que pagó y se guarda sólo hasheado.
    anonimo = models.BooleanField(default=False)
    nonce_hash = models.CharField(max_length=64, blank=True, default="")
    cuenta_nueva = models.BooleanField(default=False)
    canjeado_at = models.DateTimeField(null=True, blank=True)
    # RF5b: la unidad comprada saldó una deuda de la cuenta y no quedó derecho
    # con qué escribir el informe. Lo pone el webhook en el mismo átomo que el
    # otorgamiento (con o sin cuenta al abrir); el estado del checkout y el
    # canje anónimo lo devuelven para que la web no espere un informe que no
    # va a arrancar.
    saldo_deuda = models.BooleanField(default=False)
    # La disputa que retiró los fondos de esta compra (`charge.dispute.*`,
    # spec cobro-brl-pix RF15). Único: es la idempotencia del evento. Una fila
    # con disputa no se entrega aunque después llegue su `completed` (EC16:
    # medido el 13-10-2026 que la disputa puede llegar antes).
    disputa_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pasarela__in=["stripe", "mercadopago"]),
                name="pasarelacheckout_pasarela_valida",
            ),
        ]

    def precio_de_lista(self) -> int:
        """El precio con el que se abrió, en `self.moneda`. Las filas sin él
        caen al catálogo EN SU MONEDA; la migración `0037` se lo completó a
        todas las anteriores (que son `usd`)."""
        if self.precio_centavos is not None:
            return self.precio_centavos
        from api.catalogo import producto

        return producto(self.codigo_producto).precio_en(self.moneda)

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
            if prod.es_gratis:
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
    #: La moneda de los dos montos de arriba.
    moneda = models.CharField(max_length=3, default="usd")
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


class SolicitudArrepentimiento(models.Model):
    """Un pedido del botón de arrepentimiento (Res. SCI 424/2020). Se guarda
    para responderlo dentro del plazo; el reembolso lo hace el admin a mano
    desde la pasarela y el webhook revoca el derecho (mini-spec del 19-10)."""

    PENDIENTE = "pendiente"
    RESUELTA = "resuelta"
    ESTADOS = [(PENDIENTE, "pendiente"), (RESUELTA, "resuelta")]

    codigo = models.CharField(max_length=12, unique=True)
    email = models.EmailField()
    numero_compra = models.CharField(max_length=40, blank=True, default="")
    locale = models.CharField(max_length=5, default="es")
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    nota_admin = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "solicitud de arrepentimiento"
        verbose_name_plural = "solicitudes de arrepentimiento"
        ordering = ["-created_at"]

    def __str__(self):
        return self.codigo


class MailBloqueado(models.Model):
    """Un mail que no entra ni compra con cuenta (RF16): el de quien disputó
    un pago. Se guarda normalizado. Una compra sin cuenta con este mail se
    acredita igual —la plata ya entró— y avisa al admin (R8). Alta y baja a
    mano desde el admin; `funds_reinstated` lo da de baja solo."""

    email = models.EmailField(unique=True)
    motivo = models.CharField(max_length=40)
    dispute_id = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "mail bloqueado"
        verbose_name_plural = "mails bloqueados"

    @staticmethod
    def normalizar(email: str) -> str:
        return (email or "").strip().lower()

    @classmethod
    def bloqueado(cls, email: str) -> bool:
        limpio = cls.normalizar(email)
        return bool(limpio) and cls.objects.filter(email=limpio).exists()

    @classmethod
    def bloquear(cls, email: str, motivo: str, dispute_id: str = "") -> None:
        limpio = cls.normalizar(email)
        if limpio:
            cls.objects.get_or_create(email=limpio, defaults={"motivo": motivo, "dispute_id": dispute_id})

    def __str__(self):
        return f"{self.email} ({self.motivo})"


class Reembolso(models.Model):
    """Un `refund.created` de Stripe ya aplicado a una compra: la constancia
    de idempotencia del reembolso, aunque no haya revocado nada (no quedaban
    unidades, o un combo devuelto a medias). Antes la constancia era el
    `Movimiento` de `canje.revocar`, que obligaba a llamarlo con 0 unidades:
    eso sumaba al contador de reembolsos de la cuenta, que con tres la marca
    `flagged` y le cierra el checkout (revisión del 18-10-2026)."""

    refund_id = models.CharField(max_length=100, unique=True)
    fila = models.ForeignKey(
        "PasarelaCheckout", null=True, on_delete=models.SET_NULL, related_name="reembolsos",
    )
    monto = models.PositiveIntegerField()
    # Unidades que cubre este reembolso: las que revocó más las que tomó de
    # una disputa abierta que ya las había revocado.
    unidades = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "reembolso"
        verbose_name_plural = "reembolsos"

    def __str__(self):
        return f"{self.refund_id} ({self.monto})"


class Disputa(models.Model):
    """Una disputa de Stripe sobre una compra nuestra, y lo que se hizo con
    ella (RF15). Es la constancia de que el evento ya se aplicó: la marca
    `disputa_id` de la fila se borra al reponer, y los movimientos del ledger
    no existen en todas las ramas (sin entregar, ya reembolsada), así que
    ninguno de los dos alcanza para saber si un `funds_withdrawn` reentregado
    ya pasó (revisión del 18-10-2026).

    `email` es el mail que se bloqueó, normalizado y tomado al retirar: el
    bloqueo dura mientras ese mail tenga alguna disputa abierta, aunque la
    cuenta cambie de mail después. `revocado_*` dice qué se le sacó a la
    cuenta, para reponer exactamente eso y no el producto entero."""

    ABIERTA = "abierta"
    RESUELTA = "resuelta"
    ESTADOS = [(ABIERTA, "abierta"), (RESUELTA, "resuelta a favor")]

    dispute_id = models.CharField(max_length=100, unique=True)
    fila = models.ForeignKey(
        "PasarelaCheckout", null=True, on_delete=models.SET_NULL, related_name="disputas",
    )
    email = models.EmailField(blank=True, default="")
    estado = models.CharField(max_length=10, choices=ESTADOS, default=ABIERTA)
    # Lo que se le pasó a `canje.revocar` (para reponer exactamente eso) y
    # cuánto se sumó a la compra (para restarlo si Stripe devuelve los fondos).
    revocado_codigo = models.CharField(max_length=50, blank=True, default="")
    revocado_cantidad = models.PositiveIntegerField(default=0)
    revocado_entera = models.BooleanField(default=False)
    unidades_revocadas = models.PositiveIntegerField(default=0)
    monto_anotado = models.PositiveIntegerField(default=0)
    # Un reembolso posterior tomó (parte de) lo revocado: ver
    # `disputas.ceder_a_reembolso`.
    cedido_a_reembolso = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resuelta_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "disputa"
        verbose_name_plural = "disputas"
        indexes = [models.Index(fields=["email", "estado"])]

    def __str__(self):
        return f"{self.dispute_id} ({self.estado})"


class CupoDiario(models.Model):
    """Cuántas generaciones gratis se reservaron en un día (UTC) por ámbito.

    Existe porque `cache.incr` de `DatabaseCache` lee y después escribe: dos
    pedidos simultáneos podían pasar el mismo lugar del tope de gasto. Acá
    reservar es un `UPDATE ... WHERE usados < tope` y Postgres lo serializa
    (spec 2026-10-08-lectura-anonima, RF10/RF11).
    """

    AMBITOS = (("anonimo", "anonimo"), ("cuenta", "cuenta"))

    fecha = models.DateField()
    ambito = models.CharField(max_length=10, choices=AMBITOS)
    usados = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["fecha", "ambito"], name="uniq_cupo_por_dia_y_ambito"),
        ]

    def __str__(self):
        return f"{self.fecha} {self.ambito}: {self.usados}"


class ConteoDiario(models.Model):
    """Cuántas veces pasó algo en un día (UTC), contado en el servidor.

    PostHog sólo ve a quien acepta las cookies —el 10..16-10-2026, 135 personas
    contra 481 clics de Google Ads—, así que sus números son una muestra. Esto
    es el total real: una fila por día y evento con un contador, sin IP, sin
    cuenta ni ningún dato de quién fue, así que no necesita consentimiento.
    Lo escribe `api.conteo.contar`; lo lee el informe diario.
    """

    EVENTOS = (
        ("carta_calculada", "carta_calculada"),
        ("checkout_abierto", "checkout_abierto"),
        # Lo que hace quien calculó su carta sin cuenta, antes de pagar
        # (api/conteo_api.py, 20-10-2026). Los manda el navegador.
        ("teaser_datos_abiertos", "teaser_datos_abiertos"),
        ("teaser_cierre_visto", "teaser_cierre_visto"),
        ("teaser_clic_arriba", "teaser_clic_arriba"),
        ("teaser_clic_cierre", "teaser_clic_cierre"),
        ("teaser_clic_usd", "teaser_clic_usd"),
        ("teaser_clic_brl", "teaser_clic_brl"),
        ("teaser_clic_ars", "teaser_clic_ars"),
        ("teaser_mail_enviado", "teaser_mail_enviado"),
        ("teaser_volver", "teaser_volver"),
    )

    fecha = models.DateField()
    evento = models.CharField(max_length=30, choices=EVENTOS)
    cantidad = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["fecha", "evento"], name="uniq_conteo_por_dia_y_evento"),
        ]

    def __str__(self):
        return f"{self.fecha} {self.evento}: {self.cantidad}"


class ConteoProcedencia(models.Model):
    """De dónde viene quien calcula su carta, por día (UTC): canal y lugar.

    Igual que `ConteoDiario`, sin dato de quién fue. El valor nunca es lo que
    mandó el navegador: el canal es de una lista cerrada (`conteo.CANALES`) y el
    lugar sale de una zona horaria real (`conteo.lugar_de_zona`), así que la
    tabla no crece con lo que cualquiera quiera inventar.
    """

    TIPOS = (("canal", "canal"), ("lugar", "lugar"))

    fecha = models.DateField()
    tipo = models.CharField(max_length=10, choices=TIPOS)
    valor = models.CharField(max_length=64)
    cantidad = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["fecha", "tipo", "valor"], name="uniq_procedencia_por_dia"),
        ]

    def __str__(self):
        return f"{self.fecha} {self.tipo}={self.valor}: {self.cantidad}"


class EntradaCache(models.Model):
    """La tabla de `DatabaseCache`, para que `purgar_codigos_acceso` borre lo
    vencido por el ORM y no con SQL armado a mano. No gestionada: la crea y
    la usa `createcachetable`/`DatabaseCache`, nunca una migración. La tabla
    es la `LOCATION` que fija `config/caches.py` (un test lo ata)."""

    cache_key = models.CharField(max_length=255, primary_key=True)
    value = models.TextField()
    expires = models.DateTimeField(db_index=True)

    class Meta:
        managed = False
        db_table = "django_cache"
