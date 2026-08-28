from django.urls import path

from api.sessions import LogoutView
from api.views import (
    AccountView,
    AppleAuthView,
    ChartCollectionView,
    ChartDetailView,
    GeocodeView,
    GoogleAuthView,
    InterpretationEstadoView,
    InterpretationView,
)
from api.pdf import ChartPdfView
from api.sky import SkyView
from api.webhooks import RevenueCatWebhookView

urlpatterns = [
    path("account/", AccountView.as_view()),
    path("charts/", ChartCollectionView.as_view()),
    path("charts/<uuid:uuid>/", ChartDetailView.as_view()),
    path("charts/<uuid:uuid>/interpretation/", InterpretationView.as_view()),
    path("charts/<uuid:uuid>/interpretation/estado", InterpretationEstadoView.as_view()),
    path("charts/<uuid:uuid>/pdf/", ChartPdfView.as_view()),
    path("geocode/", GeocodeView.as_view()),
    path("sky/", SkyView.as_view()),
    path("auth/apple", AppleAuthView.as_view()),
    path("auth/google", GoogleAuthView.as_view()),
    path("auth/logout", LogoutView.as_view()),
    path("webhooks/revenuecat", RevenueCatWebhookView.as_view()),
]
