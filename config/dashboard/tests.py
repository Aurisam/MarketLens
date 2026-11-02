from types import SimpleNamespace
from io import StringIO
from unittest.mock import Mock, patch

import requests
from django.template.loader import render_to_string
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from . import services
from .models import Candle, Instrument


class MarketDataTests(SimpleTestCase):
    @patch("dashboard.services.requests.get")
    def test_binance_price_request(self, mock_get):
        mock_get.return_value = Mock(json=Mock(return_value={"price": "123.45"}))

        self.assertEqual(services.get_crypto_price("BTC"), 123.45)
        mock_get.assert_called_once_with(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": "BTCUSDT"},
            timeout=10,
        )
        mock_get.return_value.raise_for_status.assert_called_once()

    @patch("dashboard.services.requests.get")
    def test_binance_api_failure_returns_no_data(self, mock_get):
        mock_get.side_effect = requests.RequestException("API unavailable")

        self.assertIsNone(services.get_crypto_price("BTC"))
        self.assertEqual(services.get_binance_candles("BTC"), [])

    @patch("dashboard.services.requests.post")
    def test_hyperliquid_price_request(self, mock_post):
        mock_post.return_value = Mock(json=Mock(return_value={"BTC": "123.45"}))

        self.assertEqual(services.get_hyperliquid_price("BTC"), 123.45)
        mock_post.assert_called_once_with(
            "https://api.hyperliquid.xyz/info",
            json={"type": "allMids", "dex": ""},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

    @patch("dashboard.services.time.time", return_value=123)
    @patch("dashboard.services.requests.post")
    def test_hyperliquid_candles_request_and_limit(self, mock_post, mock_time):
        mock_post.return_value = Mock(json=Mock(return_value=[{"t": 1}, {"t": 2}]))

        self.assertEqual(services.get_hyperliquid_candles("BTC", "4h", 1), [{"t": 2}])
        mock_post.assert_called_once_with(
            "https://api.hyperliquid.xyz/info",
            json={
                "type": "candleSnapshot",
                "req": {"coin": "BTC", "interval": "4h", "startTime": 0, "endTime": 123000},
            },
            timeout=10,
        )

    @patch("dashboard.services.requests.post")
    def test_hyperliquid_api_failure_returns_no_data(self, mock_post):
        mock_post.side_effect = requests.RequestException("API unavailable")

        self.assertIsNone(services.get_hyperliquid_price("BTC"))
        self.assertEqual(services.get_hyperliquid_candles("BTC"), [])

    def test_both_sources_produce_the_same_candle_format(self):
        instrument = SimpleNamespace(symbol="BTC", data_source="Binance")
        with patch("dashboard.services.get_binance_candles", return_value=[[1000, "10", "12", "9", "11"]]):
            binance_candles = services.get_instrument_candles(instrument)

        instrument.data_source = "Hyperliquid"
        with patch("dashboard.services.get_hyperliquid_candles", return_value=[
            {"t": 1000, "o": "10", "h": "12", "l": "9", "c": "11"}
        ]):
            hyperliquid_candles = services.get_instrument_candles(instrument)

        self.assertEqual(binance_candles, [
            {"open_time": 1000, "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0}
        ])
        self.assertEqual(binance_candles, hyperliquid_candles)


class DashboardTemplateTests(SimpleTestCase):
    def test_each_instrument_has_its_own_buttons_and_chart_data(self):
        timeframes = ["1h", "4h", "1d"]
        chart = {"labels": [1000], "prices": [12], "sma20": [None], "sma50": [None], "rsi": [None]}
        instrument = {
            "name": "Bitcoin", "symbol": "BTC", "instrument_type": "Crypto",
            "price_available": False,
            "rsi": {"1h": {"rsi": 0}, "4h": None, "1d": {"rsi": 55}},
            "chart_data": {timeframe: chart for timeframe in timeframes},
        }
        html = render_to_string("dashboard/home.html", {
            "instruments": [instrument, instrument], "timeframes": timeframes,
        })

        for instrument_id in [1, 2]:
            for timeframe in timeframes:
                self.assertIn(f"changeTimeframe({instrument_id}, '{timeframe}', this)", html)
            self.assertIn(f'id="price-chart-{instrument_id}"', html)
            self.assertIn(f'id="rsi-chart-{instrument_id}"', html)
        self.assertEqual(html.count('class="btn btn-outline-primary active"'), 2)
        self.assertIn('data-chart-4h-prices="12"', html)
        self.assertIn('data-chart-1d-rsi="None"', html)
        self.assertIn('/static/dashboard/charts.js', html)
        self.assertIn("Price unavailable", html)
        self.assertIn("N/A", html)

    def test_empty_dashboard(self):
        html = render_to_string("dashboard/home.html", {"instruments": []})
        self.assertIn("No instruments added yet.", html)


class StoredMarketDataTests(TestCase):
    def setUp(self):
        self.instrument = Instrument.objects.create(
            name="Bitcoin", symbol="BTC", instrument_type="Crypto", data_source="Binance",
        )
        self.candles = [
            {"open_time": index * 3600000, "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0}
            for index in range(60)
        ]

    def update_data(self):
        call_command("update_market_data", stdout=StringIO(), stderr=StringIO())

    @patch("dashboard.management.commands.update_market_data.get_instrument_price", return_value=11)
    @patch("dashboard.management.commands.update_market_data.get_instrument_candles")
    def test_repeated_updates_replace_the_open_candle_without_duplicates(self, candles, price):
        candles.return_value = self.candles
        self.update_data()
        self.candles[-1]["close"] = 12.0
        self.update_data()
        self.assertEqual(Candle.objects.count(), 180)
        self.assertEqual(Candle.objects.filter(interval="1h").latest("open_time").close, 12.0)
        self.instrument.refresh_from_db()
        self.assertEqual(self.instrument.last_price, 11)
        self.assertIsNotNone(self.instrument.data_updated_at)

    @patch("dashboard.management.commands.update_market_data.get_instrument_price", return_value=11)
    @patch("dashboard.management.commands.update_market_data.get_instrument_candles")
    def test_failure_keeps_saved_data_and_can_be_retried(self, candles, price):
        candles.return_value = self.candles
        self.update_data()
        self.instrument.refresh_from_db()
        last_update = self.instrument.data_updated_at
        candles.side_effect = [[], self.candles, self.candles]
        price.return_value = None
        with self.assertRaises(CommandError):
            self.update_data()
        self.instrument.refresh_from_db()
        self.assertEqual(Candle.objects.count(), 180)
        self.assertEqual(self.instrument.last_price, 11)
        self.assertEqual(self.instrument.data_updated_at, last_update)
        candles.side_effect = None
        price.return_value = 11
        self.update_data()

    @patch("dashboard.management.commands.update_market_data.get_instrument_price", return_value=11)
    @patch("dashboard.management.commands.update_market_data.get_instrument_candles")
    def test_page_uses_database_without_any_external_requests(self, candles, price):
        candles.return_value = self.candles
        self.update_data()
        with patch("requests.get", side_effect=AssertionError("Unexpected external request")), patch(
            "requests.post", side_effect=AssertionError("Unexpected external request"),
        ):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        instrument = list(response.context["instruments"])[0]
        self.assertEqual(instrument.chart_data["1h"]["labels"], [c["open_time"] for c in self.candles])
        self.assertEqual(instrument.sma["1h"]["sma50"], 11)
        self.assertContains(response, "$11.00")

    def test_page_with_no_saved_data(self):
        with patch("requests.get", side_effect=AssertionError("Unexpected external request")):
            response = self.client.get("/")
        self.assertContains(response, "Waiting for the first full data update.")
        self.assertContains(response, "Price unavailable")
