"""Puslapiai skaito istoriją iš DB; atskiras kainų maršrutas tikrina naujausias Yahoo kainas."""

from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .models import Instrument
from .forms import AddInstrumentForm
from .watchlist import get_personal_ids, set_personal_ids, visible_instruments, register_instrument, PERSONAL_LIMIT
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


def get_dashboard_instruments(request=None):
    """Prideda instrumentams grafikų duomenis, indikatorius, signalus ir duomenų senumo žymą."""
    instruments = visible_instruments(request).select_related("fundamentals")

    for instrument in instruments:
        instrument.is_personal = not instrument.is_public
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
        instrument.analysis_rows = []

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
            instrument.analysis_rows.append({
                "timeframe": timeframe,
                "weight": {"1h": 1, "4h": 2, "1d": 3}[timeframe],
                "sma": instrument.sma[timeframe],
                "rsi": instrument.rsi[timeframe],
                "analysis": instrument.signals[timeframe],
            })

        instrument.overall_signal = get_overall_signal(
            instrument.signals
        )

        instrument.signal_consensus = get_signal_consensus(
            instrument.signals
        )
        instrument.fundamental_data = getattr(instrument, "fundamentals", None)
        instrument.fundamental_url = f"https://finance.yahoo.com/quote/{quote(instrument.symbol, safe='')}/key-statistics/"
        if instrument.fundamental_data:
            saved = instrument.fundamental_data
            saved.revenue_growth_percent = saved.revenue_growth * 100 if saved.revenue_growth is not None else None
            saved.earnings_growth_percent = saved.earnings_growth * 100 if saved.earnings_growth is not None else None

        # SMA analizėje išsaugome ir to paties intervalo paprastą kryptį.
        for timeframe, analysis in instrument.sma.items():
            if analysis:
                analysis["trend"] = instrument.trends.get(
                    timeframe,
                    "No data",
                )

    return instruments


@never_cache
@require_GET
def home(request):
    """Grąžina visą pradinį puslapį su visų instrumentų kortelėmis."""
    return render_home(request)


def render_home(request, form=None, status=200):
    """Paruošia puslapį tiek pirmai užklausai, tiek pridėjimo formos klaidoms."""
    return render(request, "dashboard/home.html", {
        "instruments": get_dashboard_instruments(request),
        "add_instrument_form": form if form is not None else AddInstrumentForm(),
        "personal_limit": PERSONAL_LIMIT,
    }, status=status)


@require_POST
def add_instrument(request):
    """Patikrina simbolį ir prideda jį tik į šios naršyklės pasirašytą sąrašą."""
    form = AddInstrumentForm(request.POST)
    if not form.is_valid():
        return render_home(request, form, status=400)
    ids = list(Instrument.objects.filter(pk__in=get_personal_ids(request), is_public=False).values_list("pk", flat=True))
    source, symbol = form.cleaned_data["source"], form.cleaned_data["symbol"]
    existing = Instrument.objects.filter(data_source=source, symbol__iexact=symbol).first()
    if existing and (existing.is_public or existing.pk in ids):
        messages.info(request, "This instrument is already in your list.")
        return redirect("home")
    if len(ids) >= PERSONAL_LIMIT:
        form.add_error(None, f"Your personal list can contain up to {PERSONAL_LIMIT} extra instruments. Remove one first.")
        return render_home(request, form, status=400)
    try:
        instrument = register_instrument(source, symbol)
    except ValidationError as error:
        form.add_error(None, error)
        return render_home(request, form, status=400)
    if not instrument.is_public:
        ids.append(instrument.pk)
    response = redirect("home")
    set_personal_ids(response, ids)
    messages.success(request, f"{instrument.symbol} was added to this browser's list.")
    return response


@require_POST
def remove_instrument(request, instrument_id):
    """Pašalina tik ID iš šios naršyklės sąrašo; kitų lankytojų pasirinkimų ir bendros istorijos nekeičia."""
    ids = get_personal_ids(request)
    if instrument_id in ids:
        ids.remove(instrument_id)
        messages.success(request, "Instrument removed from this browser's list.")
    response = redirect("home")
    set_personal_ids(response, ids)
    return response


@never_cache
@require_GET
def dashboard_data(request):
    """Grąžina tik kortelių HTML, kurį naršyklė naudoja automatiniam atnaujinimui."""
    return render(request, "dashboard/cards.html", {"instruments": get_dashboard_instruments(request)})


@never_cache
@require_GET
def stock_prices(request):
    """Grąžina tik išsaugotų Yahoo instrumentų kainas; istorinių grafikų ir DB nekeičia."""
    instruments = list(visible_instruments(request).filter(data_source="YahooFinance"))
    # Iki keturių nepriklausomų HTTP užklausų vienu metu neleidžia ilgesniam sąrašui laukti po 5 s už kiekvieną akciją.
    # DB skaitoma pagrindiniame sraute; pagalbiniai srautai gauna tik simbolius ir grąžina API duomenis.
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(get_stock_quote, [instrument.symbol for instrument in instruments]))
    quotes = [{"id": instrument.id, "quote": value} for instrument, value in zip(instruments, values)]
    # None reiškia užklausos nesėkmę; naršyklė tokiu atveju palieka ankstesnę kainą.
    return JsonResponse({"quotes": quotes})
