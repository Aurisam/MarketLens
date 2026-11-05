"""Instrument modelis registruojamas Django administravimo skydelyje."""

from django.contrib import admin
from .models import Instrument

admin.site.register(Instrument)