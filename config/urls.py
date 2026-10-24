"""Root URL configuration for Fill-Up Fuel Route Planner API."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.urls", namespace="api")),
]
