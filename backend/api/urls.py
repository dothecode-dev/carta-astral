from django.urls import path

from api.views import (
    AccountView,
    AppleAuthView,
    ChartCollectionView,
    ChartDetailView,
    GeocodeView,
    GoogleAuthView,
    InterpretationView,
)
from api.webhooks import RevenueCatWebhookView

urlpatterns = [
    path("account/", AccountView.as_view()),
    path("charts/", ChartCollectionView.as_view()),
    path("charts/<uuid:uuid>/", ChartDetailView.as_view()),
    path("charts/<uuid:uuid>/interpretation/", InterpretationView.as_view()),
    path("geocode/", GeocodeView.as_view()),
    path("auth/apple", AppleAuthView.as_view()),
    path("auth/google", GoogleAuthView.as_view()),
    path("webhooks/revenuecat", RevenueCatWebhookView.as_view()),
]
