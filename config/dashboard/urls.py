from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('data/', views.dashboard_data, name='dashboard_data'),
    path('prices/', views.stock_prices, name='stock_prices'),
    path('instruments/add/', views.add_instrument, name='add_instrument'),
    path('instruments/<int:instrument_id>/remove/', views.remove_instrument, name='remove_instrument'),
]
