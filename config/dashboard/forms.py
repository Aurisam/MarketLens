"""Viešos instrumento pridėjimo formos laukų ir simbolio tikrinimas."""

from django import forms


class AddInstrumentForm(forms.Form):
    """Vartotojas nurodo simbolį ir platformą; pavadinimas bei tipas patikrinami pačioje platformoje."""

    source = forms.ChoiceField(
        label="Market",
        choices=[
            ("YahooFinance", "Stock or ETF · Yahoo Finance"),
            ("Binance", "Crypto · Binance (USDT pairs)"),
            ("Hyperliquid", "Crypto · Hyperliquid perpetuals"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    symbol = forms.RegexField(
        label="Symbol",
        regex=r"^[A-Za-z0-9][A-Za-z0-9.-]{0,19}$",
        max_length=20,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "AAPL, SPY, BTC or HYPE",
        }),
    )

    def clean(self):
        """Suvienodina raidžių dydį ir leidžia Binance įvesti tiek BTC, tiek BTCUSDT."""
        values = super().clean()
        if values.get("symbol"):
            symbol = values["symbol"].upper()
            if values.get("source") == "Binance":
                symbol = symbol.removesuffix("USDT")
            if not symbol:
                self.add_error("symbol", "Enter the coin symbol, for example BTC.")
            else:
                values["symbol"] = symbol
        return values
