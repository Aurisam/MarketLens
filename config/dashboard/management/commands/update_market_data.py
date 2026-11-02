import math

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from dashboard.models import Candle, Instrument
from dashboard.services import get_instrument_candles, get_instrument_price, get_instrument_timeframes


class Command(BaseCommand):
    help = "Fetch market data and save it to the database. Safe to run repeatedly."

    def handle(self, *args, **options):
        failures = 0
        for instrument_id in Instrument.objects.values_list("id", flat=True):
            # PostgreSQL serializes updates to the same instrument if two jobs overlap.
            with transaction.atomic():
                instrument = Instrument.objects.select_for_update().get(pk=instrument_id)
                complete = True
                for interval in get_instrument_timeframes(instrument):
                    candles = get_instrument_candles(instrument, interval=interval, limit=100)
                    if not candles:
                        complete = False
                        self.stderr.write(f"{instrument.symbol} {interval}: no data; keeping saved candles.")
                        continue

                    rows = [Candle(instrument=instrument, interval=interval, **candle) for candle in candles]
                    Candle.objects.bulk_create(
                        rows,
                        update_conflicts=True,
                        unique_fields=["instrument", "interval", "open_time"],
                        update_fields=["open", "high", "low", "close"],
                    )
                    self.stdout.write(f"{instrument.symbol} {interval}: saved {len(rows)} candles.")

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

        if failures:
            raise CommandError(f"{failures} instruments were only partially updated. Saved data was kept.")
