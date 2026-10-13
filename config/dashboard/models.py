from django.db import models

class Instrument(models.Model):

    INSTRUMENT_TYPES = [
        ('Crypto', 'Crypto'),
        ('Stock', 'Stock'),
        ('ETF', 'ETF'),
    ]

    DATA_SOURCES = [
        ('Binance', 'Binance'),
        ('Hyperliquid', 'Hyperliquid'),
    ]

    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=20)

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

