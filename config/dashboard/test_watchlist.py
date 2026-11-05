"""Asmeninio sąrašo atskyrimas tarp naršyklių, simbolių tikrinimas ir duomenų kiekio ribos."""

from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase
from django.utils import timezone

from .forms import AddInstrumentForm
from .models import Instrument, Candle
from .services import get_instrument_details
from .watchlist import COOKIE_NAME, active_instruments, save_candles, PERSONAL_LIMIT


class InstrumentLookupTests(SimpleTestCase):
    """Patikrina, kad platformos atsakymas, o ne vartotojas, nustato instrumento tipą."""

    def setUp(self):
        """Išvalo simbolių kešą tarp testų."""
        cache.clear()

    def test_form_normalizes_symbols_and_rejects_paths(self):
        """Normalizuoja BTCUSDT ir atmeta į simbolį nepanašų tekstą ar savavališką šaltinį."""
        form = AddInstrumentForm({"source": "Binance", "symbol": "btcusdt"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["symbol"], "BTC")
        self.assertFalse(AddInstrumentForm({"source": "YahooFinance", "symbol": "https://example.com"}).is_valid())
        self.assertFalse(AddInstrumentForm({"source": "Other", "symbol": "BTC"}).is_valid())

    @patch("dashboard.services.requests.get")
    def test_yahoo_detects_etf_and_caches_verified_metadata(self, request):
        """ETF nustatomas iš instrumentType; to paties simbolio patikra pakartotinai nekviečia API."""
        request.return_value = Mock(json=Mock(return_value={"chart": {"result": [{"meta": {
            "symbol": "QQQ", "instrumentType": "ETF", "longName": "Invesco QQQ",
        }}]}}))
        self.assertEqual(get_instrument_details("QQQ", "YahooFinance"), {"name": "Invesco QQQ", "instrument_type": "ETF"})
        get_instrument_details("QQQ", "YahooFinance")
        self.assertEqual(request.call_count, 1)

    @patch("dashboard.services.requests.get")
    def test_binance_requires_an_active_usdt_pair(self, request):
        """Neaktyvi pora neįtraukiama į vartotojo sąrašą."""
        request.return_value = Mock(json=Mock(return_value={"symbols": [{"baseAsset": "ETH", "quoteAsset": "USDT", "status": "BREAK"}]}))
        self.assertIsNone(get_instrument_details("ETH", "Binance"))

    @patch("dashboard.services.requests.post")
    def test_hyperliquid_preserves_the_exchange_symbol_case(self, request):
        """Platformos kPEPE simbolis išsaugomas toks, kokio laukia jos kainų ir žvakių srautai."""
        request.return_value = Mock(json=Mock(return_value={"universe": [{"name": "kPEPE"}]}))
        self.assertEqual(get_instrument_details("KPEPE", "Hyperliquid")["symbol"], "kPEPE")


class PersonalWatchlistTests(TestCase):
    """Dvi atskiros Client naršyklės neturi matyti viena kitos privačių instrumentų."""

    def setUp(self):
        """Sukuria bendrą instrumentą ir tinklo pakaitalus naujo instrumento istorijai."""
        cache.clear()
        self.public = Instrument.objects.create(name="Bitcoin", symbol="BTC", instrument_type="Crypto", data_source="Binance")
        self.other_browser = Client()
        self.details_patch = patch("dashboard.watchlist.get_instrument_details", return_value={"name": "Apple", "instrument_type": "Stock"})
        self.candles_patch = patch("dashboard.watchlist.get_instrument_candles", return_value=[
            {"open_time": 1000, "open": 10, "high": 12, "low": 9, "close": 11},
            {"open_time": 2000, "open": 11, "high": 13, "low": 10, "close": 12},
        ])
        self.details = self.details_patch.start()
        self.candles = self.candles_patch.start()
        self.addCleanup(self.details_patch.stop)
        self.addCleanup(self.candles_patch.stop)

    def add_apple(self, browser=None):
        """Pateikia pridėjimo formą pasirinktai testinei naršyklei."""
        return (browser or self.client).post("/instruments/add/", {"source": "YahooFinance", "symbol": "aapl"})

    def test_added_instrument_is_private_in_pages_refresh_and_quotes(self):
        """Visi skaitymo maršrutai laikosi to paties naršyklės sąrašo, o pradinės žvakės įrašomos iš karto."""
        response = self.add_apple()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.cookies[COOKIE_NAME]["httponly"])
        self.assertEqual(response.cookies[COOKIE_NAME]["samesite"], "Lax")
        added = Instrument.objects.get(symbol="AAPL")
        self.assertFalse(added.is_public)
        self.assertEqual(added.candles.count(), 6)
        self.assertIsNotNone(added.data_updated_at)
        self.assertContains(self.client.get("/"), "Apple (AAPL)")
        self.assertNotContains(self.other_browser.get("/"), "Apple (AAPL)")
        self.assertNotContains(self.other_browser.get("/data/"), "Apple (AAPL)")
        with patch("dashboard.views.get_stock_quote", return_value=None) as quote:
            self.assertEqual(self.other_browser.get("/prices/").json()["quotes"], [])
            quote.assert_not_called()
            self.assertEqual(self.client.get("/prices/").json()["quotes"][0]["id"], added.pk)

    def test_multiple_browsers_reuse_one_instrument_and_one_history(self):
        """Pakartotinis pridėjimas ir antras lankytojas nesukuria registro ar žvakių dublikatų."""
        self.add_apple()
        self.add_apple()
        self.add_apple(self.other_browser)
        self.assertEqual(Instrument.objects.filter(symbol="AAPL").count(), 1)
        self.assertEqual(Candle.objects.count(), 6)
        self.details.assert_called_once()
        self.assertEqual(self.candles.call_count, 3)

    def test_removal_does_not_delete_shared_history_or_other_browsers_choice(self):
        """Pašalinimas paveikia tik vienos naršyklės slapuką."""
        self.add_apple()
        self.add_apple(self.other_browser)
        added = Instrument.objects.get(symbol="AAPL")
        response = self.client.post(f"/instruments/{added.pk}/remove/")
        self.assertEqual(response.status_code, 302)
        self.assertNotContains(self.client.get("/"), "Apple (AAPL)")
        self.assertContains(self.other_browser.get("/"), "Apple (AAPL)")
        self.assertEqual(added.candles.count(), 6)

    def test_tampered_cookie_cannot_select_a_private_instrument(self):
        """Neužtenka į slapuką įrašyti žinomą ID – jis turi turėti serverio parašą."""
        self.add_apple()
        added = Instrument.objects.get(symbol="AAPL")
        self.other_browser.cookies[COOKIE_NAME] = str(added.pk)
        self.assertNotContains(self.other_browser.get("/"), "Apple (AAPL)")

    def test_failed_lookup_or_history_does_not_create_an_empty_instrument(self):
        """Netinkami ir laikinai nepasiekiami simboliai nepalieka tuščių DB įrašų."""
        self.details.return_value = None
        self.assertEqual(self.add_apple().status_code, 400)
        self.assertEqual(Instrument.objects.count(), 1)
        cache.clear()
        self.details.return_value = {"name": "Apple", "instrument_type": "Stock"}
        self.candles.return_value = []
        self.assertEqual(self.add_apple().status_code, 400)
        self.assertEqual(Instrument.objects.count(), 1)

    def test_personal_and_catalog_limits_stop_more_network_requests(self):
        """Pasiekus ribą API tikrinimas nepradedamas ir neribojamas jau esamų simbolių pakartotinis naudojimas."""
        with patch("dashboard.views.PERSONAL_LIMIT", 0):
            self.assertEqual(self.add_apple().status_code, 400)
        with patch("dashboard.watchlist.CATALOG_LIMIT", 1):
            self.assertEqual(self.add_apple().status_code, 400)
        self.details.assert_not_called()

    def test_add_remove_require_post_and_csrf(self):
        """Viešai keičiančios užklausos negali būti paprasti GET ar POST be CSRF žetono."""
        self.assertEqual(self.client.get("/instruments/add/").status_code, 405)
        self.assertEqual(self.client.get(f"/instruments/{self.public.pk}/remove/").status_code, 405)
        browser = Client(enforce_csrf_checks=True)
        self.assertEqual(browser.post("/instruments/add/", {"source": "Binance", "symbol": "ETH"}).status_code, 403)

    def test_private_history_is_bounded_and_inactive_symbols_are_skipped(self):
        """Privatiems simboliams paliekama 100 žvakių, o bendroji istorija ir aktyvumas vertinami atskirai."""
        self.add_apple()
        added = Instrument.objects.get(symbol="AAPL")
        candles = [{"open_time": index * 3600000, "open": 10, "high": 12, "low": 9, "close": 11} for index in range(150)]
        save_candles(added, "1h", candles)
        save_candles(self.public, "1h", candles)
        self.assertEqual(added.candles.filter(interval="1h").count(), 100)
        self.assertEqual(self.public.candles.count(), 150)
        Instrument.objects.filter(pk=added.pk).update(last_requested_at=timezone.now() - timedelta(days=8))
        self.assertNotIn(added.pk, active_instruments().values_list("pk", flat=True))
        self.client.get("/")
        self.assertIn(added.pk, active_instruments().values_list("pk", flat=True))
