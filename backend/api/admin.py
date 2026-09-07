"""Panel de consulta para operar sin pedir la terminal de Coolify.

Dos reglas que gobiernan este archivo:

1. **SÓLO LECTURA.** Nada se crea, edita ni borra desde acá. Las mutaciones van
   por management command (`grant_credits`, `delete_account`), que quedan
   versionadas, testeadas y con rastro. Un panel web que edita saldos es una
   superficie de error y de abuso que no hace falta.

   **La única excepción es `Cupon`** (06-09-2026): se crea y se edita desde acá,
   nunca se borra. Un cupón no mueve saldo —define una regla de precio— y el
   admin es el único lugar donde se ve el precio final de cada producto antes
   de publicarlo. `CuponUso`, la constancia de quién lo usó, sigue siendo sólo
   lectura. `tests/api/test_admin.py` fija las dos cosas.

2. **NADA DE DATOS DE NACIMIENTO.** `BirthData` no se registra, y `Chart` no
   expone nombre, fecha, hora ni coordenadas. Es exactamente lo que la privacy
   policy promete que no circula y lo que el scrubbing de Sentry ya protege:
   sería incoherente cuidarlo en la telemetría y exhibirlo en un panel.

`Account` no es el `User` de Django: para entrar hace falta un usuario de staff
aparte (`manage.py createsuperuser`).
"""

import secrets

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from api import canje, cupones, stripe_client
from api.catalogo import CATALOGO, producto
from api.models import (
    Account, Chart, CreditTransaction, Cupon, CuponUso, Derecho, Interpretation, Movimiento,
)


class SoloLectura(admin.ModelAdmin):
    """Base sin alta, edición ni borrado."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SoloLecturaInline(admin.TabularInline):
    """Base de inline sin alta, edición ni borrado — el mismo criterio que
    `SoloLectura`, que no aplica a los inlines por herencia."""

    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class DerechoInline(SoloLecturaInline):
    """Lo que la cuenta PUEDE hacer hoy: la primera pregunta de cualquier
    consulta de soporte, y la que el panel no podía responder desde que
    salieron los dos contadores viejos de `Account`."""

    model = Derecho
    fields = ("codigo_producto", "cantidad_restante", "vigente_hasta", "updated_at")
    readonly_fields = fields
    ordering = ("codigo_producto",)


class MovimientoInline(SoloLecturaInline):
    """Por qué le queda eso: el libro que reconstruye cada `Derecho`."""

    model = Movimiento
    fields = ("created_at", "codigo_producto", "tipo", "origen", "cantidad", "external_id", "note")
    readonly_fields = fields
    ordering = ("-created_at",)


class CreditTransactionInline(SoloLecturaInline):
    """El libro del modelo de cobro viejo, congelado y sin escritores. Sigue
    acá porque una consulta puede ser sobre algo que pasó antes del canje."""

    model = CreditTransaction
    fields = ("created_at", "kind", "lot", "amount", "external_id", "note")
    readonly_fields = fields
    ordering = ("-created_at",)


@admin.register(Account)
class AccountAdmin(SoloLectura):
    # `deuda` en la lista: es lo que la cuenta debe tras un reembolso de algo
    # que ya consumió, y desde que salieron los dos contadores viejos era el
    # único número de plata que no se veía en ningún lado del panel.
    list_display = (
        "id", "email", "email_verified", "deuda", "refund_count", "flagged", "created_at",
    )
    list_filter = ("email_verified", "flagged")
    search_fields = ("email", "id")
    readonly_fields = list_display + ("proveedores",)
    # `DerechoInline` primero: responder "no me acreditaron" empieza por ver
    # qué le queda a la cuenta, y recién después por qué. `CreditTransaction`
    # es el libro viejo, congelado, y queda al final por eso.
    inlines = [DerechoInline, MovimientoInline, CreditTransactionInline]

    @admin.display(description="proveedores SSO")
    def proveedores(self, obj):
        return ", ".join(f"{i.provider}" for i in obj.identities.all()) or "—"


@admin.register(Chart)
class ChartAdmin(SoloLectura):
    """Sin el bloque `birth`: nombre, fecha, hora y lugar no se muestran."""

    list_display = ("id", "uuid", "account", "house_system", "zodiac", "lecturas", "created_at")
    list_filter = ("house_system", "zodiac")
    search_fields = ("uuid", "account__id", "account__email")
    # `data` queda fuera a propósito: es el JSON astronómico, del que se puede
    # reconstruir el momento y el lugar de nacimiento.
    fields = ("uuid", "account", "house_system", "zodiac", "engine_version", "created_at")
    readonly_fields = fields

    @admin.display(description="lecturas")
    def lecturas(self, obj):
        return obj.interpretations.count()


@admin.register(Interpretation)
class InterpretationAdmin(SoloLectura):
    """Sin el texto: la lectura habla de la persona y no hace falta leerla para
    operar. Lo que importa acá es qué se generó, en qué idioma y con qué versión."""

    list_display = ("id", "chart", "account", "lang", "prompt_version", "created_at")
    list_filter = ("lang", "prompt_version")
    search_fields = ("chart__uuid", "account__id")
    fields = ("chart", "account", "lang", "prompt_version", "content_key", "created_at")
    readonly_fields = fields


@admin.register(CreditTransaction)
class CreditTransactionAdmin(SoloLectura):
    """El ledger viejo, histórico: `SubTombstone` lo referencia y no se borra,
    pero ya no se acredita nada acá — eso es `Movimiento`, abajo."""

    list_display = ("id", "account", "kind", "lot", "amount", "external_id", "created_at")
    list_filter = ("kind", "lot")
    search_fields = ("external_id", "account__id", "account__email")
    readonly_fields = list_display + ("interpretation", "note")


@admin.register(Derecho)
class DerechoAdmin(SoloLectura):
    """Lo que cada cuenta puede usar. Es la fuente de verdad del cobro desde
    el modelo de canje: `canje.canjear()` sólo consume de acá, dejando que
    `SinDerecho` frene al que no alcanza. `canje.puede()` existe para tests,
    no lo llama ninguna vista ni pantalla en producción."""

    list_display = (
        "id", "account", "codigo_producto", "cantidad_restante", "vigente_hasta", "updated_at",
    )
    list_filter = ("codigo_producto",)
    search_fields = ("account__id", "account__email", "codigo_producto")
    readonly_fields = list_display + ("created_at",)


@admin.register(Movimiento)
class MovimientoAdmin(SoloLectura):
    """El ledger del modelo de canje: para cuadrar contra el dashboard de
    RevenueCat y para responder "no me acreditaron" sin la CLI."""

    list_display = (
        "id", "account", "codigo_producto", "tipo", "origen",
        "cantidad", "external_id", "created_at",
    )
    list_filter = ("tipo", "origen", "codigo_producto")
    search_fields = ("external_id", "account__id", "account__email")
    readonly_fields = list_display + ("chart", "note")


# GeoName y GeoNameToken NO se registran: son millones de filas de un dataset
# público y el changelist los pagina igual, pero no aportan nada operativo.
admin.site.site_header = "ASTRA — consulta"
admin.site.site_title = "ASTRA"
admin.site.index_title = "Sólo lectura. Las mutaciones van por management command."


# --- Cupones: la excepción a la regla 1 -------------------------------------


def _dolares(centavos: int) -> str:
    # Espacio duro: que el precio no se parta de su símbolo al final de línea.
    return f"US$\u00a0{centavos // 100},{centavos % 100:02d}"


def _productos_con_precio():
    return [p for p in CATALOGO.values() if p.precio_centavos > 0]


def codigo_propuesto() -> str:
    """Un código que no se adivina, para el cupón que se manda por privado a
    una persona puntual. Editable: el de Instagram se elige a mano."""
    return secrets.token_urlsafe(9).upper().replace("_", "-")


class CuponForm(forms.ModelForm):
    productos = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple, help_text="Qué productos abarca.",
    )

    class Meta:
        model = Cupon
        fields = ["codigo", "descripcion", "porcentaje", "productos", "usos_maximos", "activo", "vence_el"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # En la ficha de un cupón creado `productos` es sólo lectura: se saca
        # del form a mano, porque un campo declarado en la clase entra aunque
        # el admin no lo pida (y quedaría «requerido» sin estar en la página).
        if self.instance.pk:
            self.fields.pop("productos", None)
        if "productos" in self.fields:
            self.fields["productos"].choices = [
                (p.codigo, f"{p.codigo} — {_dolares(p.precio_centavos)}") for p in _productos_con_precio()
            ]
        if not self.instance.pk:
            self.fields["codigo"].initial = codigo_propuesto()


class FalloStripe(Exception):
    """Stripe no acompañó el cambio: se aborta la transacción del admin entera."""


class CuponUsoInline(SoloLecturaInline):
    """Quién usó este cupón: en la ficha del cupón, con la cuenta legible y
    los montos en dólares, no en centavos."""

    model = CuponUso
    fields = ("cuenta", "codigo_producto", "descuento", "pagado", "external_id", "revocado_at", "created_at")
    readonly_fields = fields

    @admin.display(description="cuenta")
    def cuenta(self, obj):
        if obj.account is None:
            return "cuenta borrada"
        return f"{obj.account_id} · {obj.account.email or 'sin mail'}"

    @admin.display(description="descuento")
    def descuento(self, obj):
        return _dolares(obj.descuento_centavos)

    @admin.display(description="pagado")
    def pagado(self, obj):
        return _dolares(obj.monto_pagado_centavos)


@admin.register(Cupon)
class CuponAdmin(admin.ModelAdmin):
    """Escribible, con dos límites: no se borra (se desactiva) y, una vez
    creado, no se editan porcentaje, productos, tope ni vencimiento, porque
    Stripe tampoco lo permite. Para cambiar eso: desactivar y crear otro."""

    form = CuponForm
    list_display = ("codigo", "porcentaje", "productos_texto", "usos", "vence_el", "activo", "created_at")
    list_filter = ("activo",)
    search_fields = ("codigo", "descripcion")
    inlines = [CuponUsoInline]

    class Media:
        js = ("admin/cupon_preview.js",)
        css = {"all": ("admin/cupon.css",)}

    # Explícitos, para que `test_admin.py` los interrogue igual que a los de
    # sólo lectura. Entrar al panel ya exige staff: acá no se afina más.
    def has_add_permission(self, request):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return False

    def get_inlines(self, request, obj=None):
        return [] if obj is None else self.inlines  # sin cupón no hay usos que mostrar

    def get_fieldsets(self, request, obj=None):
        """El alta es un formulario; la ficha es para LEER el cupón: primero
        qué es, después lo poco que se edita, después lo derivado."""
        if obj is None:
            return (
                (None, {"fields": (
                    "codigo", "descripcion", "porcentaje", "productos", "usos_maximos",
                    "activo", "vence_el", "precios_resultantes",
                )}),
            )
        return (
            (None, {"fields": ("codigo", "porcentaje", "productos_texto", "usos_maximos", "vence_el", "usos")}),
            ("Estado", {
                "fields": ("activo", "descripcion"),
                "description": (
                    "Porcentaje, productos, tope y vencimiento no se editan: Stripe no lo "
                    "permite una vez creado el cupón. Para cambiarlos, desactivá este y creá "
                    "otro (puede llevar el mismo código)."
                ),
            }),
            ("Precio final por producto", {"fields": ("precios_resultantes",)}),
            ("Stripe", {
                "fields": ("stripe_coupon_id", "stripe_promotion_code_id", "created_at"),
                "classes": ("collapse",),
            }),
        )

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ("precios_resultantes",)
        return (
            "codigo", "porcentaje", "productos_texto", "usos_maximos", "vence_el", "usos",
            "precios_resultantes", "stripe_coupon_id", "stripe_promotion_code_id", "created_at",
        )

    @admin.display(description="productos")
    def productos_texto(self, obj):
        return ", ".join(obj.productos)

    @admin.display(description="usos")
    def usos(self, obj):
        return f"{obj.usos_confirmados()} / {obj.usos_maximos}"

    @admin.display(description="precio final por producto")
    def precios_resultantes(self, obj):
        """La tabla ya dibujada para un cupón guardado; en el alta, el
        contenedor que llena `cupon_preview.js` mientras se escribe."""
        filas = ""
        if obj is not None and obj.pk and obj.productos:
            filas = format_html_join(
                "", "<tr><td>{}</td><td>{}</td><td>−{}</td><td><b>{}</b></td></tr>",
                (
                    (codigo, _dolares(prod.precio_centavos), _dolares(descuento), _dolares(final))
                    for codigo, prod, (final, descuento) in (
                        (c, producto(c), cupones.precio_final(producto(c).precio_centavos, obj.porcentaje))
                        for c in obj.productos if c in CATALOGO
                    )
                ),
            )
            filas = format_html("<table><tr><th>producto</th><th>lista</th><th>descuento</th><th>final</th></tr>{}</table>", filas)
        # Absoluta y por `reverse`: en el alta Django pasa un `Cupon()` sin
        # guardar (no `None`), y una URL relativa resuelta desde `/add/` y
        # desde `/<pk>/change/` no cae en el mismo lugar. Falló en staging.
        url = reverse("admin:api_cupon_precios")
        return format_html('<div id="cupon-precios" data-url="{}">{}</div>', url, filas or "—")

    def get_urls(self):
        return [
            path("precios/", self.admin_site.admin_view(self.precios_view), name="api_cupon_precios"),
            *super().get_urls(),
        ]

    def precios_view(self, request):
        """`GET ?porcentaje=30&productos=a&productos=b` → el precio final de
        cada uno, con la misma función que después cobra el checkout."""
        try:
            porcentaje = int(request.GET.get("porcentaje", ""))
            if not 1 <= porcentaje <= 100:
                raise ValueError
        except ValueError:
            return JsonResponse({"error": "porcentaje"}, status=400)
        precios = []
        for codigo in request.GET.getlist("productos"):
            prod = CATALOGO.get(codigo)
            if prod is None or prod.precio_centavos <= 0:
                continue
            final, descuento = cupones.precio_final(prod.precio_centavos, porcentaje)
            precios.append({"codigo": codigo, "lista": prod.precio_centavos, "final": final, "descuento": descuento})
        return JsonResponse({"precios": precios})

    def save_model(self, request, obj, form, change):
        """El alta publica en Stripe; el cambio sólo puede tocar `descripcion`
        y `activo`. Si Stripe falla, se revierte la transacción del admin y
        no queda nada a medias: ni cupón sin espejo, ni fila que Stripe no
        reconoce."""
        if not change:
            super().save_model(request, obj, form, change)
            try:
                cupones.publicar(obj)
            except stripe_client.StripeError as exc:
                self._fallo(request, f"Stripe no pudo crear el cupón ({exc}). No se guardó.")
            return
        viejo = Cupon.objects.get(pk=obj.pk)
        activo_pedido = obj.activo
        obj.activo = viejo.activo
        super().save_model(request, obj, form, change)
        if activo_pedido == viejo.activo:
            return
        try:
            cupones.cambiar_activo(obj, activo_pedido)
        except cupones.NoSePuedeReactivar:
            self._fallo(request, "Stripe no deja reactivar un cupón agotado o vencido: creá otro.")
        except stripe_client.StripeError as exc:
            self._fallo(request, f"Stripe no pudo cambiar el cupón ({exc}). No se guardó.")

    def _fallo(self, request, mensaje):
        # Levantar y no `set_rollback`: después de `save_model` el admin
        # todavía escribe (`log_addition`), y con la transacción marcada
        # eso explota. La excepción atraviesa el `atomic` del admin —que
        # revierte todo— y la agarra `changeform_view`.
        raise FalloStripe(mensaje)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except FalloStripe as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(request.path)


@admin.register(CuponUso)
class CuponUsoAdmin(SoloLectura):
    """Quién usó qué. La única acción es revocar un regalo del 100 %, que es
    el único uso sin pago detrás y por lo tanto sin `refund.created` que lo
    revoque solo."""

    list_display = (
        "id", "cupon", "account", "codigo_producto", "descuento_centavos",
        "monto_pagado_centavos", "revocado_at", "created_at",
    )
    list_filter = ("cupon", "codigo_producto")
    search_fields = ("external_id", "account__id", "account__email", "cupon__codigo")
    readonly_fields = list_display + ("checkout", "external_id")
    actions = ["revocar_regalo"]

    def has_revocar_permission(self, request):
        return request.user.is_superuser

    @admin.action(description="Revocar el regalo (sólo cupones del cien por ciento)", permissions=["revocar"])
    def revocar_regalo(self, request, queryset):
        revocados = 0
        for uso in queryset.select_related("cupon", "account"):
            if uso.cupon.porcentaje < 100 or uso.revocado_at is not None or uso.account is None:
                continue
            canje.revocar(uso.account, uso.codigo_producto, 1, external_id=f"revoca:{uso.pk}")
            uso.revocado_at = timezone.now()
            uso.save(update_fields=["revocado_at"])
            revocados += 1
        self.message_user(request, f"{revocados} regalo(s) revocado(s).")
