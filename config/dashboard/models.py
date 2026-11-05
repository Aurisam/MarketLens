"""Duomenų bazės lentelės instrumentams ir jų kainų žvakėms."""

from django.db import models


class Instrument(models.Model):
    """Stebimas aktyvas, jo šaltinis ir paskutinė DB išsaugota kaina."""
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

    # Kaina ir jos laikas atnaujinami gavus kainą; data_updated_at tik sėkmingai gavus visus intervalus.
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
        """Administravimo sąraše pateikia pavadinimą ir biržos simbolį."""
        return self.name + ' (' + self.symbol + ')'


class StockFundamentals(models.Model):
    """Kartą per parą tikrinami akcijos rodikliai; trūkstamos reikšmės saugomos kaip NULL."""

    instrument = models.OneToOneField(Instrument, on_delete=models.CASCADE, related_name="fundamentals")
    trailing_pe = models.FloatField(null=True, blank=True)
    forward_pe = models.FloatField(null=True, blank=True)
    # Augimas saugomas dalimis: 0.15 reiškia 15 %, o -0.10 reiškia -10 %.
    revenue_growth = models.FloatField(null=True, blank=True)
    earnings_growth = models.FloatField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=30, default="Yahoo Finance")
    updated_at = models.DateTimeField(null=True, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    last_fetch_succeeded = models.BooleanField(default=False)

    def __str__(self):
        """Nurodo, kuriam instrumentui priklauso fundamentiniai duomenys."""
        return f"{self.instrument.symbol} fundamentals"


class Candle(models.Model):
    """Saugo vieno instrumento vieno intervalo OHLC žvakę ir jos pradžios laiką."""
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE, related_name="candles")
    interval = models.CharField(max_length=2, choices=[("1h", "1h"), ("4h", "4h"), ("1d", "1d")])
    # Unix laikas milisekundėmis leidžia vienodai saugoti visų API žvakių pradžią.
    open_time = models.BigIntegerField()
    # OHLC: pradžios, didžiausia, mažiausia ir uždarymo kaina per žvakės intervalą.
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()

    class Meta:
        """Neleidžia išsaugoti dviejų to paties instrumento, intervalo ir pradžios laiko žvakių."""
        constraints = [
            models.UniqueConstraint(
                fields=["instrument", "interval", "open_time"],
                name="unique_instrument_candle",
            ),
        ]
