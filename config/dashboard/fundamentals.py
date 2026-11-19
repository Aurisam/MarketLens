"""Yahoo company metrics and their refresh schedule."""

import math
from datetime import datetime, timedelta, timezone as datetime_timezone
from urllib.parse import quote

import requests
from django.utils import timezone

from .models import StockFundamentals
from .watchlist import active_instruments


def read_number(value, positive=False):
    """Read a finite Yahoo number, optionally requiring a positive value."""
    if isinstance(value, dict):
        value = value.get("raw")
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or (positive and number <= 0):
        return None
    return number


def get_stock_fundamentals(symbol):
    """Fetch P/E and growth metrics, or return None on failure."""
    # Yahoo requires a session cookie and a matching temporary crumb token.
    try:
        with requests.Session() as session:
            session.headers.update({"User-Agent": "Mozilla/5.0"})
            session.get("https://fc.yahoo.com", timeout=10)
            token = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=10)
            token.raise_for_status()
            crumb = token.text.strip()
            if not crumb or len(crumb) > 100 or "<" in crumb:
                return None
            response = session.get(
                f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{quote(symbol, safe='')}",
                params={"modules": "summaryDetail,defaultKeyStatistics,financialData", "crumb": crumb},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()["quoteSummary"]["result"][0]
            summary = data.get("summaryDetail", {})
            statistics = data.get("defaultKeyStatistics", {})
            financial = data.get("financialData", {})
            result = {
                "trailing_pe": read_number(summary.get("trailingPE"), positive=True),
                "forward_pe": read_number(statistics.get("forwardPE"), positive=True),
                "revenue_growth": read_number(financial.get("revenueGrowth")),
                "earnings_growth": read_number(financial.get("earningsGrowth")),
                "period_end": None,
            }
            period = read_number(statistics.get("mostRecentQuarter"), positive=True)
            if period is not None:
                result["period_end"] = datetime.fromtimestamp(period, datetime_timezone.utc).date()
            if not any(result[field] is not None for field in (
                "trailing_pe", "forward_pe", "revenue_growth", "earnings_growth"
            )):
                return None
            return result
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError, OSError):
        return None


def refresh_stock_fundamentals(force=False):
    """Refresh daily after success; retry failures after one hour."""
    updated = 0
    failed = 0
    for instrument in active_instruments().filter(instrument_type="Stock", data_source="YahooFinance"):
        saved, _ = StockFundamentals.objects.get_or_create(instrument=instrument)
        now = timezone.now()
        retry_after = timedelta(days=1) if saved.last_fetch_succeeded else timedelta(hours=1)
        if not force and saved.checked_at and now - saved.checked_at < retry_after:
            continue
        values = get_stock_fundamentals(instrument.symbol)
        saved.checked_at = timezone.now()
        saved.last_fetch_succeeded = values is not None
        if values is not None:
            for field, value in values.items():
                setattr(saved, field, value)
            saved.updated_at = saved.checked_at
            updated += 1
        else:
            failed += 1
        saved.save()
    return {"updated": updated, "failed": failed}
