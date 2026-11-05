"""Dashboard maršrutai: visas puslapis, kortelių HTML ir naujausių Yahoo kainų JSON."""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('data/', views.dashboard_data, name='dashboard_data'),
    path('prices/', views.stock_prices, name='stock_prices'),
]
