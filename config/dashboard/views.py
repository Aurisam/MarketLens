from django.shortcuts import render
from .models import Instrument
from .services import (get_instrument_price,
                       get_multi_timeframe_trends,
                       get_multi_timeframe_sma,
                       get_multi_timeframe_rsi,
                       get_timeframe_signal,
                       get_overall_signal)


def home(request):
    instruments = Instrument.objects.all()

    for instrument in instruments:
        instrument.price = get_instrument_price(instrument)
        instrument.trends = get_multi_timeframe_trends(instrument)
        instrument.sma = get_multi_timeframe_sma(instrument)
        instrument.rsi = get_multi_timeframe_rsi(instrument)

        instrument.signals = {}

        for timeframe in ["1h", "4h", "1d"]:
            instrument.signals[timeframe] = get_timeframe_signal(
                instrument.trends.get(timeframe),
                instrument.sma.get(timeframe),
                instrument.rsi.get(timeframe),
            )

            instrument.overall_signal = get_overall_signal(
                instrument.signals
            )

        for timeframe, analysis in instrument.sma.items():
            if analysis:
                analysis["trend"] = instrument.trends.get(
                    timeframe,
                    "No data"
                )

    return render(request,
                  'dashboard/home.html',
                  {
                "instruments": instruments,
                          },
                  )
