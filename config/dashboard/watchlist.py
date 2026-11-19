"""Personal browser selections and shared candle storage."""

from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Candle, Instrument
from .services import TIMEFRAMES, get_instrument_candles, get_instrument_details

COOKIE_NAME = "marketlens-instruments"
COOKIE_SALT = "dashboard.watchlist"
COOKIE_AGE = 365 * 24 * 60 * 60
PERSONAL_LIMIT = 10
CATALOG_LIMIT = 30
PRIVATE_CANDLE_LIMIT = 100
ACTIVE_DAYS = 7


def get_personal_ids(request):
    """Read signed instrument IDs; invalid cookies produce an empty list."""
    if request is None:
        return []
    saved = request.get_signed_cookie(COOKIE_NAME, default="", salt=COOKIE_SALT, max_age=COOKIE_AGE)
    ids = []
    for value in saved.split(","):
        if value.isascii() and value.isdigit() and len(value) <= 10:
            instrument_id = int(value)
            if instrument_id not in ids:
                ids.append(instrument_id)
        if len(ids) == PERSONAL_LIMIT:
            break
    return ids


def set_personal_ids(response, ids):
    """Save personal selections in a signed, HttpOnly cookie."""
    value = ",".join(str(instrument_id) for instrument_id in ids)
    response.set_signed_cookie(
        COOKIE_NAME,
        value,
        salt=COOKIE_SALT,
        max_age=COOKIE_AGE,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
    )


def visible_instruments(request=None):
    """Select public and personal instruments and track daily activity."""
    ids = get_personal_ids(request)
    now = timezone.now()
    Instrument.objects.filter(pk__in=ids, is_public=False).filter(
        Q(last_requested_at__isnull=True) | Q(last_requested_at__lt=now - timedelta(days=1))
    ).update(last_requested_at=now)
    return Instrument.objects.filter(Q(is_public=True) | Q(pk__in=ids)).order_by("pk")


def active_instruments():
    """Skip private instruments unused for seven days."""
    active_since = timezone.now() - timedelta(days=ACTIVE_DAYS)
    return Instrument.objects.filter(Q(is_public=True) | Q(last_requested_at__gte=active_since))


def save_candles(instrument, interval, candles):
    """Upsert candles and retain only the latest 100 per private interval."""
    rows = [Candle(instrument=instrument, interval=interval, **candle) for candle in candles]
    Candle.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["instrument", "interval", "open_time"],
        update_fields=["open", "high", "low", "close"],
    )
    if not instrument.is_public:
        saved = Candle.objects.filter(instrument=instrument, interval=interval)
        keep = list(saved.order_by("-open_time").values_list("pk", flat=True)[:PRIVATE_CANDLE_LIMIT])
        saved.exclude(pk__in=keep).delete()


def register_instrument(source, symbol):
    """Reuse an existing symbol or verify and save its initial history."""
    existing = Instrument.objects.filter(data_source=source, symbol__iexact=symbol).first()
    if existing:
        Instrument.objects.filter(pk=existing.pk).update(last_requested_at=timezone.now())
        return existing
    if Instrument.objects.count() >= CATALOG_LIMIT:
        raise ValidationError("The site's instrument capacity is currently full. Existing symbols can still be added.")
    if not cache.add("instrument-registration-slot", True, timeout=3):
        raise ValidationError("Please wait a few seconds before adding another new symbol.")
    details = get_instrument_details(symbol, source)
    if not details:
        raise ValidationError("Symbol not found on this market, or the source is temporarily unavailable. Check the symbol and try again.")
    name = details["name"] if isinstance(details["name"], str) else symbol
    candidate = Instrument(
        name=name[:50],
        symbol=details.get("symbol", symbol),
        data_source=source,
        instrument_type=details["instrument_type"],
        is_public=False,
    )
    history = {}
    for interval in TIMEFRAMES:
        try:
            history[interval] = get_instrument_candles(candidate, interval=interval, limit=100, timeout=5)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError):
            history[interval] = []
        if interval == "1h" and not history[interval]:
            raise ValidationError("The source could not load price history. Please try again later.")
    with transaction.atomic():
        # Serialize registrations to avoid duplicate symbols across concurrent requests.
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
