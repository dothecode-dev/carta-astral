from api.checkout import CheckoutEstadoView, CheckoutView
from api.mantenimiento import EstadoView
from api.webhooks_stripe import StripeWebhookView
from django.urls import path

from api.sessions import LogoutView
from api.views import (
    AccountView,
    AppleAuthView,
    ChartCollectionView,
    ChartDetailView,
    GeocodeView,
    GoogleAuthView,
    IndiceInformeView,
    InterpretationEstadoView,
    InterpretationView,
)
from api.pdf import ChartPdfView
from api.sky import SkyView
from api.webhooks import RevenueCatWebhookView

urlpatterns = [
    path("account/", AccountView.as_view()),
    path("checkout/", CheckoutView.as_view()),
    # Estado de una compra: lo consulta la página de retorno de Stripe.
    path("checkout/<str:checkout_id>/", CheckoutEstadoView.as_view()),
    # Con barra final: la pasarela no sigue redirects y APPEND_SLASH daría 301,
    # que cuenta como entrega fallida (ver 839ba19).
    path("webhooks/stripe/", StripeWebhookView.as_view()),
    path("charts/", ChartCollectionView.as_view()),
    path("charts/<uuid:uuid>/", ChartDetailView.as_view()),
    path("charts/<uuid:uuid>/interpretation/", InterpretationView.as_view()),
    path("charts/<uuid:uuid>/interpretation/estado/", InterpretationEstadoView.as_view()),
    path("charts/<uuid:uuid>/informe/indice/", IndiceInformeView.as_view()),
    path("charts/<uuid:uuid>/pdf/", ChartPdfView.as_view()),
    path("geocode/", GeocodeView.as_view()),
    path("sky/", SkyView.as_view()),
    # Si el sitio acepta trabajo nuevo: lo mira `make deploy` y la web.
    path("estado/", EstadoView.as_view()),
    path("auth/apple", AppleAuthView.as_view()),
    path("auth/google", GoogleAuthView.as_view()),
    path("auth/logout", LogoutView.as_view()),
    path("webhooks/revenuecat", RevenueCatWebhookView.as_view()),
]
