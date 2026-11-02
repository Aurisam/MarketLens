from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone

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
)


def home(request):
    instruments = Instrument.objects.all()

    for instrument in instruments:
        timeframes = get_instrument_timeframes(instrument)
        instrument.price = instrument.last_price
        instrument.price_available = instrument.price is not None
        instrument.data_is_stale = (
            instrument.data_updated_at is None
            or timezone.now() - instrument.data_updated_at > timedelta(minutes=30)
        )

        instrument.chart_data = {}
        instrument.trends = {}
        instrument.sma = {}
        instrument.rsi = {}
        instrument.signals = {}

        for timeframe in timeframes:
            candles = list(
                instrument.candles.filter(interval=timeframe)
                .order_by("-open_time")
                .values("open_time", "open", "high", "low", "close")[:100]
            )
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

        for timeframe, analysis in instrument.sma.items():
            if analysis:
                analysis["trend"] = instrument.trends.get(
                    timeframe,
                    "No data",
                )

    return render(
        request,
        "dashboard/home.html",
        {"instruments": instruments},
    )
