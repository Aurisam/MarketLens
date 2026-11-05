"""Dažniau atnaujinamų kainų gavimo, kešo ir atskiro JSON maršruto patikros."""

from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from .models import Candle, Instrument
from .services import get_stock_quote


class StockQuoteTests(SimpleTestCase):
    """Tikrina Yahoo metaduomenis atskirai nuo istorinių žvakių gavimo."""

    def setUp(self):
        """Išvalo kešą, kad vieno testo atsakymas nepaveiktų kito."""
        cache.clear()

    @patch("dashboard.services.requests.get")
    def test_quote_uses_latest_metadata_and_reuses_short_cache(self, request):
        """Kaina imama iš meta, o pakartotinis kvietimas nekuria naujos HTTP užklausos."""
        request.return_value = Mock(json=Mock(return_value={"chart": {"result": [{
            "meta": {"regularMarketPrice": 123.45, "regularMarketTime": 1700000000, "currency": "USD"},
            "indicators": {"quote": [{"close": [99]}]},
        }]}}))
        quote = get_stock_quote("SPY")
        self.assertEqual(quote["price"], 123.45)
        self.assertEqual(quote["price_time"], 1700000000000)
        self.assertEqual(quote["currency"], "USD")
        self.assertEqual(get_stock_quote("SPY"), quote)
        request.assert_called_once_with(
            "https://query1.finance.yahoo.com/v8/finance/chart/SPY",
            params={"interval": "1m", "range": "1d"},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=5,
        )

    @patch("dashboard.services.requests.get")
    def test_failed_request_is_cached_briefly_and_can_be_retried(self, request):
        """API nesėkmė negrąžina klaidingos kainos ir trumpam pristabdo kartotinius kvietimus."""
        request.side_effect = requests.RequestException("Rate limited")
        self.assertIsNone(get_stock_quote("SPY"))
        self.assertIsNone(get_stock_quote("SPY"))
        self.assertEqual(request.call_count, 1)
        # Kešo pašalinimas imituoja jo galiojimo pabaigą be laukimo teste.
        cache.delete("stock-quote:SPY")
        self.assertIsNone(get_stock_quote("SPY"))
        self.assertEqual(request.call_count, 2)

    @patch("dashboard.services.requests.get")
    def test_invalid_prices_and_missing_metadata_return_no_quote(self, request):
        """Atmetamos netinkamos kainos, laikas ir valiuta, kad nepilni duomenys nepatektų į naršyklę."""
        for meta in [
            {}, {"regularMarketPrice": None, "regularMarketTime": 1700000000},
            {"regularMarketPrice": float("nan"), "regularMarketTime": 1700000000},
            {"regularMarketPrice": -1, "regularMarketTime": 1700000000},
            {"regularMarketPrice": 20, "regularMarketTime": None},
            {"regularMarketPrice": 20, "regularMarketTime": 10 ** 30},
            {"regularMarketPrice": 20, "regularMarketTime": 1700000000, "currency": None},
        ]:
            with self.subTest(meta=meta):
                cache.clear()
                request.return_value = Mock(json=Mock(return_value={"chart": {"result": [{"meta": meta}]}}))
                self.assertIsNone(get_stock_quote("SPY"))


class StockPriceViewTests(TestCase):
    """Tikrina, kad kainų maršrutas grąžintų tik Yahoo instrumentus ir nekeistų DB istorijos."""

    def setUp(self):
        """Sukuria skirtingų šaltinių instrumentus kainų maršruto filtravimui patikrinti."""
        self.stock = Instrument.objects.create(
            name="NVIDIA", symbol="NVDA", instrument_type="Stock", data_source="YahooFinance", last_price=10,
        )
        self.etf = Instrument.objects.create(
            name="S&P500", symbol="SPY", instrument_type="ETF", data_source="YahooFinance",
        )
        Instrument.objects.create(name="Bitcoin", symbol="BTC", instrument_type="Crypto", data_source="Binance")

    @patch("dashboard.views.get_stock_quote")
    def test_prices_include_stock_and_etf_but_do_not_write_to_database(self, quote):
        """JSON pateikia naują kainą, o anksčiau išsaugota kaina bei žvakių kiekis išlieka tie patys."""
        quote.return_value = {"price": 20, "price_time": 1000, "checked_at": 2000, "currency": "USD"}
        response = self.client.get("/prices/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["id"] for item in response.json()["quotes"]}, {self.stock.id, self.etf.id})
        self.assertEqual({call.args[0] for call in quote.call_args_list}, {"NVDA", "SPY"})
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.last_price, 10)
        self.assertEqual(Candle.objects.count(), 0)
        self.assertIn("no-store", response.headers["Cache-Control"])

    @patch("dashboard.views.get_stock_quote", return_value=None)
    def test_failure_is_reported_without_relabelling_saved_price_as_fresh(self, quote):
        """Nesėkmė grąžinama kaip null; sena DB kaina nepateikiama su nauju laiku."""
        response = self.client.get("/prices/")
        self.assertTrue(all(item["quote"] is None for item in response.json()["quotes"]))
        self.assertEqual(self.client.post("/prices/").status_code, 405)

    def test_page_contains_separate_price_controls(self):
        """Pradiniame puslapyje pateikiami ryšiui reikalingi ID, šaltiniai ir kainų modulio failas."""
        response = self.client.get("/")
        self.assertContains(response, 'data-prices-url="/prices/"')
        self.assertContains(response, 'data-source="YahooFinance" data-symbol="NVDA"')
        self.assertContains(response, 'data-live-price')
        self.assertContains(response, '/static/dashboard/prices.js')

    @patch("dashboard.views.get_stock_quote")
    def test_parallel_quotes_keep_the_correct_instrument_ids(self, quote):
        """Kelių simbolių API atsakymai nepriskiriami kitoms kortelėms, kai užklausos atliekamos kartu."""
        prices = {"NVDA": 20, "SPY": 50}
        quote.side_effect = lambda symbol: {"price": prices[symbol], "price_time": 1000, "checked_at": 2000, "currency": "USD"}
        response = self.client.get("/prices/")
        result = {item["id"]: item["quote"]["price"] for item in response.json()["quotes"]}
        self.assertEqual(result, {self.stock.id: 20, self.etf.id: 50})
