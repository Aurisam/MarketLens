"""Puslapiai skaito istoriją iš DB; atskiras kainų maršrutas tikrina naujausias Yahoo kainas."""

from datetime import timedelta

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import Instrument
from .services import (
    get_chart_data,
    get_instrument_timeframes,
    get_rsi_analysis,
    get_sma_analysis,
    get_simple_trend,
    get_overall_signal,
    get_signal_consensus,
    get_timeframe_signal,
    get_stock_quote,
)


def get_dashboard_instruments():
    """Prideda instrumentams grafikų duomenis, indikatorius, signalus ir duomenų senumo žymą."""
    instruments = Instrument.objects.all()

    for instrument in instruments:
        timeframes = get_instrument_timeframes(instrument)
        instrument.price = instrument.last_price
        instrument.price_available = instrument.price is not None
        # Po 30 minučių be pilno atnaujinimo kortelėje parodomas duomenų senumo pranešimas.
        instrument.data_is_stale = (
            instrument.data_updated_at is None
            or timezone.now() - instrument.data_updated_at > timedelta(minutes=30)
        )

        instrument.chart_data = {}
        instrument.trends = {}
        instrument.sma = {}
        instrument.rsi = {}
        instrument.signals = {}

        # Kiekvienam intervalui paruošiama atskira kainų ir indikatorių seka.
        for timeframe in timeframes:
            candles = list(
                instrument.candles.filter(interval=timeframe)
                .order_by("-open_time")
                .values("open_time", "open", "high", "low", "close")[:100]
            )
            # DB paimame 100 naujausių, o skaičiavimams apverčiame į seniausios–naujausios tvarką.
            candles.reverse()
            instrument.chart_data[timeframe] = get_chart_data(candles)
            instrument.trends[timeframe] = get_simple_trend(candles)
            instrument.sma[timeframe] = get_sma_analysis(candles)
            instrument.rsi[timeframe] = get_rsi_analysis(candles)
            instrument.signals[timeframe] = get_timeframe_signal(
                instrument.trends.get(timeframe),
                instrument.sma.get(timeframe),
                instrument.rsi.get(timeframe),
            )

        instrument.overall_signal = get_overall_signal(
            instrument.signals
        )

        instrument.signal_consensus = get_signal_consensus(
            instrument.signals
        )

        # SMA analizėje išsaugome ir to paties intervalo paprastą kryptį.
        for timeframe, analysis in instrument.sma.items():
            if analysis:
                analysis["trend"] = instrument.trends.get(
                    timeframe,
                    "No data",
                )

    return instruments


@require_GET
def home(request):
    """Grąžina visą pradinį puslapį su visų instrumentų kortelėmis."""
    return render(request, "dashboard/home.html", {"instruments": get_dashboard_instruments()})


@never_cache
@require_GET
def dashboard_data(request):
    """Grąžina tik kortelių HTML, kurį naršyklė naudoja automatiniam atnaujinimui."""
    return render(request, "dashboard/cards.html", {"instruments": get_dashboard_instruments()})


@never_cache
@require_GET
def stock_prices(request):
    """Grąžina tik išsaugotų Yahoo instrumentų kainas; istorinių grafikų ir DB nekeičia."""
    quotes = []
    for instrument in Instrument.objects.filter(data_source="YahooFinance"):
        quote = get_stock_quote(instrument.symbol)
        quotes.append({"id": instrument.id, "quote": quote})
    # None reiškia užklausos nesėkmę; naršyklė tokiu atveju palieka ankstesnę kainą.
    return JsonResponse({"quotes": quotes})
