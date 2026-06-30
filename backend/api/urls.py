from django.urls import path

from api.views import (
    AccountMeView,
    AppleAuthView,
    ChartCreateView,
    ChartDetailView,
    GeocodeView,
    GoogleAuthView,
    InstallationCreateView,
    InstallationMeView,
    InterpretationView,
)

urlpatterns = [
    path("installations/", InstallationCreateView.as_view()),
    path("installations/me/", InstallationMeView.as_view()),
    path("account/me", AccountMeView.as_view()),
    path("charts/", ChartCreateView.as_view()),
    path("charts/<uuid:uuid>/", ChartDetailView.as_view()),
    path("charts/<uuid:uuid>/interpretation/", InterpretationView.as_view()),
    path("geocode/", GeocodeView.as_view()),
    path("auth/apple", AppleAuthView.as_view()),
    path("auth/google", GoogleAuthView.as_view()),
]
