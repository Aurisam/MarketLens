"""Pagrindiniai URL: administravimo skydelis ir dashboard programėlės maršrutai."""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
]
