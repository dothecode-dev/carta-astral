from django.urls import path

from api.views import (
    ChartCreateView,
    ChartDetailView,
    GeocodeView,
    InstallationCreateView,
    InstallationMeView,
    InterpretationView,
)

urlpatterns = [
    path("installations/", InstallationCreateView.as_view()),
    path("installations/me/", InstallationMeView.as_view()),
    path("charts/", ChartCreateView.as_view()),
    path("charts/<uuid:uuid>/", ChartDetailView.as_view()),
    path("charts/<uuid:uuid>/interpretation/", InterpretationView.as_view()),
    path("geocode/", GeocodeView.as_view()),
]
