from django.urls import path

from api.views import ChartCreateView, ChartDetailView

urlpatterns = [
    path("charts/", ChartCreateView.as_view()),
    path("charts/<int:pk>/", ChartDetailView.as_view()),
]
