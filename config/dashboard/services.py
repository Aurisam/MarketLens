"""Market API requests and candle validation."""

import math
import time
from urllib.parse import quote

import requests
from django.core.cache import cache

BINANCE_API_URL = "https://data-api.binance.vision/api/v3"
HYPERLIQUID_API_URL = "https://api.hyperliquid.xyz/info"
API_TIMEOUT_SECONDS = 10
TIMEFRAMES = ("1h", "4h", "1d")


def get_instrument_details(symbol, source):
    """Verify the symbol and determine its asset type."""
    cache_key = f"instrument-details:{source}:{symbol}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached or None
    result = None
    try:
        if source == "YahooFinance":
            response = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}",
                params={"interval": "1d", "range": "1mo"},
                headers={"User-Agent": "Mozilla/5.0"}, timeout=5,
            )
            response.raise_for_status()
            meta = response.json()["chart"]["result"][0]["meta"]
            kind = {"EQUITY": "Stock", "ETF": "ETF"}.get(meta.get("instrumentType"))
            if kind and meta.get("symbol", "").upper() == symbol:
                result = {"name": meta.get("longName") or meta.get("shortName") or symbol, "instrument_type": kind}
        elif source == "Binance":
            response = requests.get(f"{BINANCE_API_URL}/exchangeInfo", params={"symbol": f"{symbol}USDT"}, timeout=5)
            response.raise_for_status()
            pair = response.json()["symbols"][0]
            if pair["baseAsset"] == symbol and pair["quoteAsset"] == "USDT" and pair["status"] == "TRADING":
                result = {"name": symbol, "instrument_type": "Crypto"}
        elif source == "Hyperliquid":
            response = requests.post(HYPERLIQUID_API_URL, json={"type": "meta"}, timeout=5)
            response.raise_for_status()
            for item in response.json()["universe"]:
                if item.get("name", "").upper() == symbol and not item.get("isDelisted"):
                    result = {"name": item["name"], "symbol": item["name"], "instrument_type": "Crypto"}
                    break
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError, AttributeError):
        result = None
    cache.set(cache_key, result or False, timeout=1800 if result else 30)
    return result


def get_stock_quote(symbol):
    """Fetch a cached Yahoo quote, or return None on failure."""
    cache_key = f"stock-quote:{symbol}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached or None

    try:
        response = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}",
            params={"interval": "1m", "range": "1d"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        response.raise_for_status()
        meta = response.json()["chart"]["result"][0]["meta"]
        price = float(meta["regularMarketPrice"])
        price_time = int(meta["regularMarketTime"]) * 1000
        checked_at = int(time.time() * 1000)
        currency = meta.get("currency", "USD")
        if (not math.isfinite(price) or price <= 0 or not 0 < price_time <= checked_at + 300000
                or not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha()):
            raise ValueError("Invalid Yahoo quote")
        result = {
            "price": price,
            "price_time": price_time,
            "checked_at": checked_at,
            # Preserve units: GBp means pence, while GBP means pounds.
            "currency": currency,
        }
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError, OverflowError):
        cache.set(cache_key, False, timeout=15)
        return None

    cache.set(cache_key, result, timeout=30)
    return result


def get_crypto_price(symbol):
    """Fetch the Binance price in USDT, or return None."""
    url = f"{BINANCE_API_URL}/ticker/price"
    params = {"symbol": f"{symbol}USDT"}

    try:
        response = requests.get(url, params=params, timeout=API_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict) or "price" not in data:
            print("Binance returned an unexpected price response.")
            return None

        price = float(data["price"])
        return price if math.isfinite(price) and price > 0 else None

    except (requests.RequestException, ValueError, TypeError, OverflowError) as error:
        print(f"Binance price API error: {error}")
        return None


def get_hyperliquid_price(symbol):
    """Fetch the Hyperliquid mid-price, or return None."""
    payload = {"type": "allMids", "dex": ""}

    try:
        response = requests.post(
            HYPERLIQUID_API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=API_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict) or symbol not in data:
            print(f"Hyperliquid price unavailable for {symbol}.")
            return None

        price = float(data[symbol])
        return price if math.isfinite(price) and price > 0 else None

    except (requests.RequestException, ValueError, TypeError, OverflowError) as error:
        print(f"Hyperliquid price API error: {error}")
        return None


def group_four_hour_candles(hourly_candles):
    """Group hourly candles within the same trading session."""
    grouped = []
    hour = 60 * 60 * 1000
    previous_time = None
    for candle in hourly_candles:
        opened = candle["open_time"]
        if not grouped or opened - previous_time > hour or opened - grouped[-1]["open_time"] >= 4 * hour:
            grouped.append(candle.copy())
        else:
            group = grouped[-1]
            group["high"] = max(group["high"], candle["high"])
            group["low"] = min(group["low"], candle["low"])
            group["close"] = candle["close"]
        previous_time = opened
    return grouped


def get_stock_candles(symbol, interval, timeout=API_TIMEOUT_SECONDS):
    """Fetch Yahoo history and build 4h candles from hourly data."""
    if interval == "4h":
        return group_four_hour_candles(get_stock_candles(symbol, "1h", timeout=timeout))

    ranges = {"1h": "3mo", "1d": "6mo"}
    if interval not in ranges:
        return []

    cache_key = f"stock-candles:{symbol}:{interval}"
    candles = cache.get(cache_key)
    if candles is not None:
        return candles

    try:
        response = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}",
            params={"interval": interval, "range": ranges[interval]},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
        )
        response.raise_for_status()
        result = response.json()["chart"]["result"][0]
        prices = result["indicators"]["quote"][0]
        candles = []
        for index, timestamp in enumerate(result["timestamp"]):
            try:
                candles.append({
                    "open_time": int(timestamp) * 1000,
                    "open": prices["open"][index],
                    "high": prices["high"][index],
                    "low": prices["low"][index],
                    "close": prices["close"][index],
                })
            except (KeyError, IndexError, TypeError, ValueError, OverflowError):
                continue
        candles = validate_candles(candles)
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        candles = []

    cache.set(cache_key, candles, timeout=300 if candles else 30)
    return candles


def get_instrument_price(instrument):
    if instrument.data_source == "Hyperliquid":
        return get_hyperliquid_price(instrument.symbol)

    if instrument.data_source == "Binance":
        return get_crypto_price(instrument.symbol)

    if instrument.data_source == "YahooFinance":
        candles = get_stock_candles(instrument.symbol, "1h")
        if candles:
            return candles[-1]["close"]

    return None


def get_binance_candles(symbol, interval="1h", limit=100, timeout=API_TIMEOUT_SECONDS):
    """Fetch raw Binance candles, or return an empty list."""
    url = f"{BINANCE_API_URL}/klines"
    params = {
        "symbol": f"{symbol}USDT",
        "interval": interval,
        "limit": limit,
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()

    except (requests.RequestException, ValueError) as error:
        print(f"Binance candles API error: {error}")
        return []

    if not isinstance(data, list):
        print("Binance returned an unexpected response.")
        return []

    return data


def get_hyperliquid_candles(symbol, interval="1h", limit=100, timeout=API_TIMEOUT_SECONDS):
    """Fetch at most the requested number of Hyperliquid candles."""
    end_time_ms = int(time.time() * 1000)
    interval_ms = {"1h": 3600000, "4h": 14400000, "1d": 86400000}.get(interval)
    if interval_ms is None or limit <= 0:
        return []

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": symbol,
            "interval": interval,
            "startTime": max(0, end_time_ms - limit * interval_ms),
            "endTime": end_time_ms,
        },
    }

    try:
        response = requests.post(
            HYPERLIQUID_API_URL,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()

    except (requests.RequestException, ValueError) as error:
        print(f"Hyperliquid candles API error: {error}")
        return []

    if not isinstance(data, list):
        print("Hyperliquid returned an unexpected response.")
        return []

    return data[-limit:]


def get_formatted_hyperliquid_candles(symbol, interval="1h", limit=100, timeout=API_TIMEOUT_SECONDS):
    """Convert Hyperliquid fields to the common candle format."""
    candles = get_hyperliquid_candles(symbol, interval=interval, limit=limit, timeout=timeout)

    formatted_candles = []

    for candle in candles:
        try:
            formatted_candles.append({
                "open_time": candle["t"],
                "open": candle["o"],
                "high": candle["h"],
                "low": candle["l"],
                "close": candle["c"],
            })
        except (KeyError, TypeError):
            continue

    return formatted_candles


def get_formatted_binance_candles(symbol, interval="1h", limit=100, timeout=API_TIMEOUT_SECONDS):
    """Convert Binance positions to named candle fields."""
    candles = get_binance_candles(symbol, interval=interval, limit=limit, timeout=timeout)

    formatted_candles = []

    for candle in candles:
        try:
            formatted_candles.append({
                "open_time": candle[0],
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
            })
        except (IndexError, KeyError, TypeError):
            continue

    return formatted_candles


def get_instrument_candles(instrument, interval="1h", limit=100, timeout=API_TIMEOUT_SECONDS):
    """Select the source and return validated candles."""
    if interval not in TIMEFRAMES or limit <= 0:
        return []
    if instrument.data_source == "YahooFinance":
        return get_stock_candles(instrument.symbol, interval, timeout=timeout)[-limit:]
    if instrument.data_source == "Binance":
        candles = get_formatted_binance_candles(
            instrument.symbol,
            interval=interval,
            limit=limit,
            timeout=timeout,
        )
    elif instrument.data_source == "Hyperliquid":
        candles = get_formatted_hyperliquid_candles(
            instrument.symbol,
            interval=interval,
            limit=limit,
            timeout=timeout,
        )
    else:
        return []

    return validate_candles(candles)


def validate_candles(candles):
    """Reject invalid candles, remove duplicates and sort by opening time."""
    if not isinstance(candles, list):
        return []

    valid_candles = {}

    for candle in candles:
        if not isinstance(candle, dict):
            continue

        try:
            open_price = float(candle["open"])
            high_price = float(candle["high"])
            low_price = float(candle["low"])
            close_price = float(candle["close"])
            open_time = int(candle["open_time"])

        except (KeyError, TypeError, ValueError, OverflowError):
            continue

        prices = [
            open_price,
            high_price,
            low_price,
            close_price,
        ]

        if not all(math.isfinite(price) for price in prices):
            continue

        if min(prices) <= 0:
            continue

        if low_price > min(open_price, close_price):
            continue

        if high_price < max(open_price, close_price):
            continue

        if low_price > high_price:
            continue

        if open_time < 0:
            continue

        valid_candles[open_time] = {
            "open_time": open_time,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
        }

    return sorted(valid_candles.values(), key=lambda candle: candle["open_time"])
