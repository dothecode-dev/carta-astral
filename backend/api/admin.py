"""Panel de consulta para operar sin pedir la terminal de Coolify.

Dos reglas que gobiernan este archivo:

1. **SÓLO LECTURA.** Nada se crea, edita ni borra desde acá. Las mutaciones van
   por management command (`grant_credits`, `delete_account`), que quedan
   versionadas, testeadas y con rastro. Un panel web que edita saldos es una
   superficie de error y de abuso que no hace falta.

2. **NADA DE DATOS DE NACIMIENTO.** `BirthData` no se registra, y `Chart` no
   expone nombre, fecha, hora ni coordenadas. Es exactamente lo que la privacy
   policy promete que no circula y lo que el scrubbing de Sentry ya protege:
   sería incoherente cuidarlo en la telemetría y exhibirlo en un panel.

`Account` no es el `User` de Django: para entrar hace falta un usuario de staff
aparte (`manage.py createsuperuser`).
"""

from django.contrib import admin

from api.models import Account, Chart, CreditTransaction, Interpretation, Movimiento


class SoloLectura(admin.ModelAdmin):
    """Base sin alta, edición ni borrado."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CreditTransactionInline(admin.TabularInline):
    """El ledger de la cuenta: para responder "no me acreditaron" sin la CLI."""

    model = CreditTransaction
    extra = 0
    can_delete = False
    fields = ("created_at", "kind", "lot", "amount", "external_id", "note")
    readonly_fields = fields
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Account)
class AccountAdmin(SoloLectura):
    list_display = (
        "id", "email", "email_verified", "refund_count", "flagged", "created_at",
    )
    list_filter = ("email_verified", "flagged")
    search_fields = ("email", "id")
    readonly_fields = list_display + ("proveedores",)
    inlines = [CreditTransactionInline]

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
