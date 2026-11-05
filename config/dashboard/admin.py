"""Instrument modelis registruojamas Django administravimo skydelyje."""

from django.contrib import admin
from .models import Instrument, StockFundamentals

admin.site.register(Instrument)
admin.site.register(StockFundamentals)
