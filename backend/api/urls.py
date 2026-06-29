from django.urls import path

from api.views import (
    ChartCreateView,
    ChartDetailView,
    GeocodeView,
    InterpretationView,
)

urlpatterns = [
    path("charts/", ChartCreateView.as_view()),
    path("charts/<int:pk>/", ChartDetailView.as_view()),
    path("charts/<int:pk>/interpretation/", InterpretationView.as_view()),
    path("geocode/", GeocodeView.as_view()),
]
