import math

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from dashboard.models import Instrument
from dashboard.watchlist import active_instruments, save_candles
from dashboard.fundamentals import refresh_stock_fundamentals
from dashboard.services import TIMEFRAMES, get_instrument_candles, get_instrument_price


class Command(BaseCommand):
    help = "Fetch market data and save it to the database. Safe to run repeatedly."

    def handle(self, *args, **options):
        """Refresh market data while retaining saved values when a source fails."""
        failures = 0
        for instrument_id in active_instruments().values_list("id", flat=True):
            with transaction.atomic():
                instrument = Instrument.objects.select_for_update().get(pk=instrument_id)
                complete = True
                for interval in TIMEFRAMES:
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

                if complete:
                    instrument.data_updated_at = timezone.now()
                else:
                    failures += 1
                instrument.save(update_fields=["last_price", "price_updated_at", "data_updated_at"])

        fundamentals = refresh_stock_fundamentals()
        if fundamentals["failed"]:
            self.stderr.write("Some stock fundamentals are unavailable; previous values were kept.")

        # Report partial failure only after saving the successful updates.
        if failures:
            raise CommandError(f"{failures} instruments were only partially updated. Saved data was kept.")
