"""Indikatorių formulės tikrinamos su žinomomis kainomis, ne su tikro API atsakymais."""

from django.test import SimpleTestCase

from .services import (
    calculate_rsi, calculate_sma, get_chart_data, get_overall_signal,
    get_rsi_analysis, get_signal_consensus, get_sma_analysis, get_timeframe_signal,
)


def make_candles(closes):
    """Iš uždarymo kainų sudaro nuoseklų OHLC sąrašą, tinkamą skaičiavimų testams."""
    return [{"open_time": (index + 1) * 3600000, "open": close, "high": close + 1,
             "low": close - 0.5, "close": close} for index, close in enumerate(closes)]


class IndicatorTests(SimpleTestCase):
    """Tikrina SMA vidurkius, RSI glodinimą ir trūkstamų istorijos taškų apdorojimą."""

    def test_sma_uses_only_the_requested_last_closes(self):
        """Paskutinių 20 ir 50 kainų vidurkiai turi sutapti su ranka apskaičiuotais."""
        candles = make_candles(range(1, 61))
        self.assertEqual(calculate_sma(candles, 20), 50.5)
        self.assertEqual(calculate_sma(candles, 50), 35.5)
        self.assertIsNone(calculate_sma(candles[:10], 20))
        self.assertEqual(get_sma_analysis(candles), {
            "sma20": 50.5, "sma50": 35.5, "price_above_sma20": True, "price_above_sma50": True,
        })

    def test_wilder_rsi_matches_a_known_mixed_price_series(self):
        """Patikrina pirmą RSI14 ir vėlesnį Wilder atnaujinimą mišrioje kainų sekoje."""
        closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
                  45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00]
        self.assertAlmostEqual(calculate_rsi(make_candles(closes[:15])), 70.4641350211, places=8)
        self.assertAlmostEqual(calculate_rsi(make_candles(closes)), 66.2496185536, places=8)

    def test_rsi_handles_rising_falling_flat_and_short_history(self):
        """Kritimo nebuvimas, vien kritimas ir nekintanti kaina turi skirtingus RSI rezultatus."""
        for closes, expected in [(list(range(1, 31)), 100), (list(range(30, 0, -1)), 0), ([10] * 30, 50)]:
            with self.subTest(expected=expected):
                self.assertEqual(calculate_rsi(make_candles(closes)), expected)
        self.assertIsNone(calculate_rsi(make_candles([10] * 14)))
        self.assertIsNone(get_rsi_analysis([]))

    def test_chart_series_align_with_times_and_latest_indicators(self):
        """SMA ir RSI pradžios tarpai nekeičia reikšmių ir laiko indeksų atitikimo."""
        candles = make_candles([30 + index % 7 + index / 10 for index in range(60)])
        chart = get_chart_data(candles)
        self.assertTrue(all(len(values) == 60 for values in chart.values()))
        self.assertEqual(chart["labels"], [candle["open_time"] for candle in candles])
        self.assertEqual(chart["sma20"][:19], [None] * 19)
        self.assertEqual(chart["sma50"][:49], [None] * 49)
        self.assertEqual(chart["rsi"][:14], [None] * 14)
        self.assertAlmostEqual(chart["sma20"][-1], calculate_sma(candles, 20))
        self.assertEqual(chart["rsi"][-1], round(calculate_rsi(candles), 2))
        self.assertTrue(all(values == [] for values in get_chart_data([]).values()))


class SignalTests(SimpleTestCase):
    """Tikrina konkrečius balus, ribas ir bendro signalo svorius."""

    def test_all_bullish_and_all_bearish_factors_have_four_points(self):
        """Kryptis, dvi SMA pozicijos ir RSI sudaro daugiausia keturis teigiamus ar neigiamus balus."""
        for trend, above, rsi, score, signal in [
            ("Uptrend", True, 60, 4, "Bullish"), ("Downtrend", False, 40, -4, "Bearish"),
        ]:
            with self.subTest(signal=signal):
                result = get_timeframe_signal(trend, {"price_above_sma20": above, "price_above_sma50": above}, {"rsi": rsi})
                self.assertEqual(result["score"], score)
                self.assertEqual(result["signal"], signal)
                self.assertEqual(len(result["factors"]), 4)
                self.assertEqual(result["indicators_available"], 3)

    def test_rsi_boundaries_and_insufficient_indicator_groups(self):
        """45 ir 55 priklauso kryptiniams balams; vienos indikatorių grupės nepakanka signalui."""
        for rsi, score in [(45, -1), (50, 0), (55, 1)]:
            result = get_timeframe_signal("Sideways", None, {"rsi": rsi})
            self.assertEqual(result["score"], score)
            self.assertEqual(result["signal"], "Neutral")
        self.assertIsNone(get_timeframe_signal("No data", None, {"rsi": 60})["score"])

    def test_overall_uses_weights_and_counts_intervals_separately(self):
        """Trys intervalai turi svorių sumą 6, o jų svertinis vidurkis skaičiuojamas atskirai."""
        result = get_overall_signal({"1h": {"score": 4}, "4h": {"score": -4}, "1d": {"score": 2}})
        self.assertEqual(result, {"score": 0.33, "signal": "Neutral", "timeframes_used": 3, "total_weight": 6})
        self.assertEqual(get_overall_signal({"1d": {"score": 2}})["signal"], "Bullish")
        self.assertEqual(get_overall_signal({"1d": {"score": -2}})["signal"], "Bearish")
        self.assertEqual(get_overall_signal({"1d": {"score": None}})["total_weight"], 0)
        self.assertEqual(get_overall_signal({"1d": {"score": 0}})["score"], 0)

    def test_consensus_distinguishes_agreement_and_conflict(self):
        """Bendras balas ir intervalų tarpusavio sutapimas yra atskiri rezultatai."""
        self.assertEqual(get_signal_consensus({"1h": {"signal": "Bullish"}, "1d": {"signal": "Bullish"}})["alignment"], "Full agreement")
        self.assertEqual(get_signal_consensus({"1h": {"signal": "Bullish"}, "1d": {"signal": "Bearish"}})["alignment"], "Conflicting signals")
        self.assertEqual(get_signal_consensus({})["alignment"], "No data")
