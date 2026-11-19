from django.db import models


class Instrument(models.Model):
    """A tracked asset and its last saved price."""
    INSTRUMENT_TYPES = [
        ('Crypto', 'Crypto'),
        ('Stock', 'Stock'),
        ('ETF', 'ETF'),
    ]

    DATA_SOURCES = [
        ('Binance', 'Binance'),
        ('Hyperliquid', 'Hyperliquid'),
        ('YahooFinance', 'Yahoo Finance'),
    ]

    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=20)
    is_public = models.BooleanField(default=True)
    last_requested_at = models.DateTimeField(null=True, blank=True, editable=False)

    last_price = models.FloatField(null=True, blank=True, editable=False)
    price_updated_at = models.DateTimeField(null=True, blank=True, editable=False)
    data_updated_at = models.DateTimeField(null=True, blank=True, editable=False)

    instrument_type = models.CharField(
        max_length=20,
        choices=INSTRUMENT_TYPES
    )

    data_source = models.CharField(
        max_length=20,
        choices=DATA_SOURCES
    )

    def __str__(self):
        return self.name + ' (' + self.symbol + ')'


class StockFundamentals(models.Model):
    """Saved company metrics; growth is stored as a fraction, not a percentage."""

    instrument = models.OneToOneField(Instrument, on_delete=models.CASCADE, related_name="fundamentals")
    trailing_pe = models.FloatField(null=True, blank=True)
    forward_pe = models.FloatField(null=True, blank=True)
    revenue_growth = models.FloatField(null=True, blank=True)
    earnings_growth = models.FloatField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=30, default="Yahoo Finance")
    updated_at = models.DateTimeField(null=True, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    last_fetch_succeeded = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.instrument.symbol} fundamentals"


class Candle(models.Model):
    """OHLC prices with a Unix opening time in milliseconds."""
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE, related_name="candles")
    interval = models.CharField(max_length=2, choices=[("1h", "1h"), ("4h", "4h"), ("1d", "1d")])
    open_time = models.BigIntegerField()
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["instrument", "interval", "open_time"],
                name="unique_instrument_candle",
            ),
        ]
