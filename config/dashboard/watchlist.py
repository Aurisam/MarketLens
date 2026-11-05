"""Asmeninis naršyklės sąrašas ir vieną kartą serveryje saugoma bendra simbolių istorija."""

from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Candle, Instrument
from .services import get_instrument_candles, get_instrument_details

COOKIE_NAME = "marketlens-instruments"
COOKIE_SALT = "dashboard.watchlist"
COOKIE_AGE = 365 * 24 * 60 * 60
PERSONAL_LIMIT = 10
CATALOG_LIMIT = 30
PRIVATE_CANDLE_LIMIT = 100
ACTIVE_DAYS = 7


def get_personal_ids(request):
    """Perskaito pasirašytą ID sąrašą; pakeistas ar pasibaigęs slapukas laikomas tuščiu sąrašu."""
    if request is None:
        return []
    saved = request.get_signed_cookie(COOKIE_NAME, default="", salt=COOKIE_SALT, max_age=COOKIE_AGE)
    return list(dict.fromkeys(int(value) for value in saved.split(",")
                             if value.isascii() and value.isdigit() and len(value) <= 10))[:PERSONAL_LIMIT]


def set_personal_ids(response, ids):
    """Sąrašą išsaugo tik šios naršyklės slapuke; registracijos ir vartotojo DB įrašo nereikia."""
    response.set_signed_cookie(COOKIE_NAME, ",".join(str(value) for value in ids), salt=COOKIE_SALT,
                               max_age=COOKIE_AGE, httponly=True, secure=not settings.DEBUG, samesite="Lax")


def visible_instruments(request=None):
    """Atrenka bendrus ir šios naršyklės instrumentus; privataus aktyvumą pažymi ne dažniau nei kartą per parą."""
    ids = get_personal_ids(request)
    Instrument.objects.filter(pk__in=ids, is_public=False).filter(
        Q(last_requested_at__isnull=True) | Q(last_requested_at__lt=timezone.now() - timedelta(days=1))
    ).update(last_requested_at=timezone.now())
    return Instrument.objects.filter(Q(is_public=True) | Q(pk__in=ids)).order_by("pk")


def active_instruments():
    """Periodinė užduotis praleidžia privačius simbolius, kurių niekas neatidarė septynias dienas."""
    return Instrument.objects.filter(Q(is_public=True) | Q(last_requested_at__gte=timezone.now() - timedelta(days=ACTIVE_DAYS)))


def save_candles(instrument, interval, candles):
    """Atnaujina OHLC be dublikatų; privačiam instrumentui išlaiko tik 100 naujausių vieno intervalo žvakių."""
    rows = [Candle(instrument=instrument, interval=interval, **candle) for candle in candles]
    Candle.objects.bulk_create(rows, update_conflicts=True,
                               unique_fields=["instrument", "interval", "open_time"],
                               update_fields=["open", "high", "low", "close"])
    if not instrument.is_public:
        saved = Candle.objects.filter(instrument=instrument, interval=interval)
        keep = list(saved.order_by("-open_time").values_list("pk", flat=True)[:PRIVATE_CANDLE_LIMIT])
        saved.exclude(pk__in=keep).delete()


def register_instrument(source, symbol):
    """Pakartotinai naudoja bendrą registro įrašą arba patikrina platformą ir įrašo pradinę istoriją."""
    existing = Instrument.objects.filter(data_source=source, symbol__iexact=symbol).first()
    if existing:
        Instrument.objects.filter(pk=existing.pk).update(last_requested_at=timezone.now())
        return existing
    if Instrument.objects.count() >= CATALOG_LIMIT:
        raise ValidationError("The site's instrument capacity is currently full. Existing symbols can still be added.")
    # Trumpa bendra vieno serverio proceso pauzė riboja kartotines brangias tikrinimo užklausas.
    if not cache.add("instrument-registration-slot", True, timeout=3):
        raise ValidationError("Please wait a few seconds before adding another new symbol.")
    details = get_instrument_details(symbol, source)
    if not details:
        raise ValidationError("Symbol not found on this market, or the source is temporarily unavailable. Check the symbol and try again.")
    name = details["name"] if isinstance(details["name"], str) else symbol
    candidate = Instrument(name=name[:50], symbol=details.get("symbol", symbol), data_source=source,
                           instrument_type=details["instrument_type"], is_public=False)
    history = {}
    for interval in ["1h", "4h", "1d"]:
        try:
            history[interval] = get_instrument_candles(candidate, interval=interval, limit=100, timeout=5)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError):
            history[interval] = []
        # Neįrašome tuščio instrumento, jei nepavyksta gauti net pagrindinės istorijos.
        if interval == "1h" and not history[interval]:
            raise ValidationError("The source could not load price history. Please try again later.")
    with transaction.atomic():
        # PostgreSQL užraktas serializuoja pridėjimus, kad keli lankytojai nekurtų to paties simbolio kopijų.
        Instrument.objects.select_for_update().order_by("pk").first()
        existing = Instrument.objects.filter(data_source=source, symbol__iexact=symbol).first()
        if existing:
            return existing
        if Instrument.objects.count() >= CATALOG_LIMIT:
            raise ValidationError("The site's instrument capacity is currently full.")
        candidate.last_requested_at = timezone.now()
        candidate.last_price = history["1h"][-1]["close"]
        candidate.price_updated_at = timezone.now()
        if all(history.values()):
            candidate.data_updated_at = timezone.now()
        candidate.save()
        for interval, candles in history.items():
            if candles:
                save_candles(candidate, interval, candles)
    return candidate
