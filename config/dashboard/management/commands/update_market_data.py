"""Komanda python manage.py update_market_data atnaujina API duomenis bendroje duomenų bazėje."""

import math

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from dashboard.models import Instrument
from dashboard.watchlist import active_instruments, save_candles
from dashboard.fundamentals import refresh_stock_fundamentals
from dashboard.services import get_instrument_candles, get_instrument_price, get_instrument_timeframes


class Command(BaseCommand):
    """Django komanda periodiniam visų išsaugotų instrumentų atnaujinimui."""
    help = "Fetch market data and save it to the database. Safe to run repeatedly."

    def handle(self, *args, **options):
        """Įrašo naujas žvakes ir kainas; dalinės API nesėkmės atveju išsaugo turimus duomenis."""
        failures = 0
        for instrument_id in active_instruments().values_list("id", flat=True):
            # Transakcija ir eilutės užraktas neleidžia dviem PostgreSQL užduotims kartu keisti to paties instrumento.
            with transaction.atomic():
                instrument = Instrument.objects.select_for_update().get(pk=instrument_id)
                complete = True
                for interval in get_instrument_timeframes(instrument):
                    candles = get_instrument_candles(instrument, interval=interval, limit=100)
                    if not candles:
                        complete = False
                        self.stderr.write(f"{instrument.symbol} {interval}: no data; keeping saved candles.")
                        continue

                    save_candles(instrument, interval, candles)
                    self.stdout.write(f"{instrument.symbol} {interval}: saved {len(candles)} candles.")

                price = get_instrument_price(instrument)
                if price is not None and math.isfinite(price) and price > 0:
                    instrument.last_price = price
                    instrument.price_updated_at = timezone.now()
                else:
                    complete = False
                    self.stderr.write(f"{instrument.symbol}: no price; keeping saved price.")

                # Pilno atnaujinimo laikas keičiamas tik gavus visus intervalus ir tinkamą kainą.
                if complete:
                    instrument.data_updated_at = timezone.now()
                else:
                    failures += 1
                instrument.save(update_fields=["last_price", "price_updated_at", "data_updated_at"])

        # Tas pats tvarkaraštis paleidžia ir fundamentinius duomenis, bet jų helperis tikrina paros ribą.
        fundamentals = refresh_stock_fundamentals()
        if fundamentals["failed"]:
            self.stderr.write("Some stock fundamentals are unavailable; previous values were kept.")

        # Klaida pranešama jau išsaugojus sėkmingus rezultatus; GitHub Actions matys nesėkmingą vykdymą.
        if failures:
            raise CommandError(f"{failures} instruments were only partially updated. Saved data was kept.")
