"""Fundamentinių duomenų formatavimo, kasdienio atnaujinimo ir puslapio patikros."""

from datetime import date, timedelta
from unittest.mock import MagicMock, Mock, patch

import requests
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .fundamentals import get_stock_fundamentals, read_number, refresh_stock_fundamentals
from .models import Instrument, StockFundamentals


class FundamentalSourceTests(SimpleTestCase):
    """Naudoja imituotą Yahoo sesiją, todėl testams nereikia interneto ar API rakto."""

    def test_number_reader_preserves_zero_and_negative_growth(self):
        """Nulis nėra trūkstamas augimas; neigiamas ar nulinis P/E atmetamas."""
        self.assertEqual(read_number({"raw": 0}), 0)
        self.assertEqual(read_number({"raw": -0.15}), -0.15)
        for value in [None, {}, True, "invalid", float("nan"), float("inf")]:
            self.assertIsNone(read_number(value))
        self.assertIsNone(read_number(-5, positive=True))
        self.assertIsNone(read_number(0, positive=True))

    @patch("dashboard.fundamentals.requests.Session")
    def test_source_parses_raw_values_and_reporting_period(self, session_class):
        """Patikrina Yahoo laukų ir datų susiejimą bei nulio augimo išlaikymą."""
        session = MagicMock()
        session_class.return_value.__enter__.return_value = session
        session.get.side_effect = [Mock(), Mock(text="temporary-token"), Mock(json=Mock(return_value={"quoteSummary": {"result": [{
            "summaryDetail": {"trailingPE": {"raw": 25}},
            "defaultKeyStatistics": {"forwardPE": {"raw": 20}, "mostRecentQuarter": {"raw": 1785024000}},
            "financialData": {"revenueGrowth": {"raw": 0}, "earningsGrowth": {"raw": -0.15}},
        }]}}))]
        self.assertEqual(get_stock_fundamentals("NVDA"), {
            "trailing_pe": 25, "forward_pe": 20, "revenue_growth": 0,
            "earnings_growth": -0.15, "period_end": date(2026, 7, 26),
        })
        self.assertEqual(session.get.call_args.kwargs["params"]["modules"], "summaryDetail,defaultKeyStatistics,financialData")

    @patch("dashboard.fundamentals.requests.Session")
    def test_source_failure_returns_no_new_data(self, session_class):
        """Ryšio klaida nepateikiama kaip galiojantys tušti ar nuliniai rodikliai."""
        session_class.return_value.__enter__.return_value.get.side_effect = requests.RequestException("Unavailable")
        self.assertIsNone(get_stock_fundamentals("NVDA"))


class StoredFundamentalTests(TestCase):
    """Tikrina, kad fundamentalai atnaujinami retai ir pateikiami tik akcijoms."""

    def setUp(self):
        """Sukuria akciją ir ETF bei aiškias testinių rodiklių reikšmes."""
        self.stock = Instrument.objects.create(name="NVIDIA", symbol="NVDA", instrument_type="Stock", data_source="YahooFinance")
        self.etf = Instrument.objects.create(name="S&P500", symbol="SPY", instrument_type="ETF", data_source="YahooFinance")
        self.values = {"trailing_pe": 25, "forward_pe": 20, "revenue_growth": 0,
                       "earnings_growth": -0.15, "period_end": date(2026, 7, 26)}

    @patch("dashboard.fundamentals.get_stock_fundamentals")
    def test_success_is_reused_for_a_day_and_etfs_are_skipped(self, fetch):
        """Pakartotinis komandos vykdymas tą pačią parą neatlieka API užklausos."""
        fetch.return_value = self.values
        self.assertEqual(refresh_stock_fundamentals(), {"updated": 1, "failed": 0})
        self.assertEqual(refresh_stock_fundamentals(), {"updated": 0, "failed": 0})
        fetch.assert_called_once_with("NVDA")
        self.assertFalse(StockFundamentals.objects.filter(instrument=self.etf).exists())
        self.assertEqual(refresh_stock_fundamentals(force=True)["updated"], 1)

    @patch("dashboard.fundamentals.get_stock_fundamentals", return_value=None)
    def test_failure_keeps_old_values_and_retries_after_an_hour(self, fetch):
        """Nesėkmė pažymi senus duomenis, bet jų neištrina ir nekartoja užklausos kas 15 minučių."""
        previous = timezone.now() - timedelta(days=2)
        saved = StockFundamentals.objects.create(instrument=self.stock, **self.values, updated_at=previous,
                                                 checked_at=previous, last_fetch_succeeded=True)
        self.assertEqual(refresh_stock_fundamentals()["failed"], 1)
        saved.refresh_from_db()
        self.assertEqual(saved.trailing_pe, 25)
        self.assertEqual(saved.updated_at, previous)
        self.assertFalse(saved.last_fetch_succeeded)
        self.assertEqual(refresh_stock_fundamentals()["failed"], 0)
        fetch.assert_called_once()

    def test_page_shows_zero_negative_and_missing_metrics_without_api_calls(self):
        """Nulis ir neigiamas augimas rodomi skaičiais; nepateiktas forward P/E rodomas kaip No data."""
        self.values["forward_pe"] = None
        StockFundamentals.objects.create(instrument=self.stock, **self.values, updated_at=timezone.now(), last_fetch_succeeded=True)
        with patch("requests.Session", side_effect=AssertionError("Unexpected market request")):
            response = self.client.get("/")
        self.assertContains(response, "0.00%")
        self.assertContains(response, "-15.00%")
        self.assertContains(response, "No data")
        self.assertContains(response, 'data-panel="fundamentals-' + str(self.stock.id) + '"')
        self.assertNotContains(response, 'data-panel="fundamentals-' + str(self.etf.id) + '"')
        self.assertContains(response, "Why this signal?")
