import math
import time
import requests
from django.core.cache import cache
from urllib.parse import quote

BINANCE_API_URL = "https://api.binance.com/api/v3"
HYPERLIQUID_API_URL = "https://api.hyperliquid.xyz/info"
API_TIMEOUT_SECONDS = 10


def get_crypto_price(symbol):
    """Return the Binance price in USDT, or None if unavailable."""
    url = f"{BINANCE_API_URL}/ticker/price"
    params = {"symbol": f"{symbol}USDT"}

    try:
        response = requests.get(url, params=params, timeout=API_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict) or "price" not in data:
            print("Binance returned an unexpected price response.")
            return None

        return float(data["price"])

    except (requests.RequestException, ValueError, TypeError) as error:
        print(f"Binance price API error: {error}")
        return None


def get_hyperliquid_price(symbol):
    """Return the Hyperliquid midpoint price, or None if unavailable."""
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

        return float(data[symbol])

    except (requests.RequestException, ValueError, TypeError) as error:
        print(f"Hyperliquid price API error: {error}")
        return None


def group_four_hour_candles(hourly_candles):
    grouped = []
    hour = 60 * 60 * 1000
    previous_time = None
    for candle in hourly_candles:
        opened = candle["open_time"]
        # An overnight gap starts a new session, even after a short trading day.
        if not grouped or opened - previous_time > hour or opened - grouped[-1]["open_time"] >= 4 * hour:
            grouped.append(candle.copy())
        else:
            group = grouped[-1]
            group["high"] = max(group["high"], candle["high"])
            group["low"] = min(group["low"], candle["low"])
            group["close"] = candle["close"]
        previous_time = opened
    return grouped


def get_stock_candles(symbol, interval):
    """Fetch stock and ETF candles from Yahoo Finance."""
    if interval == "4h":
        return group_four_hour_candles(get_stock_candles(symbol, "1h"))

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
            timeout=API_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json()["chart"]["result"][0]
        prices = result["indicators"]["quote"][0]
        candles = []
        for index, timestamp in enumerate(result["timestamp"]):
            candles.append({
                "open_time": timestamp * 1000,
                "open": prices["open"][index],
                "high": prices["high"][index],
                "low": prices["low"][index],
                "close": prices["close"][index],
            })
        candles = validate_candles(candles)
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        candles = []

    cache.set(cache_key, candles, timeout=300 if candles else 30)
    return candles


def get_instrument_timeframes(instrument):
    return ["1h", "4h", "1d"]


def get_instrument_price(instrument):
    """Choose the price API using the instrument’s saved data source."""
    if instrument.data_source == "Hyperliquid":
        return get_hyperliquid_price(instrument.symbol)

    if instrument.data_source == "Binance":
        return get_crypto_price(instrument.symbol)

    if instrument.data_source == "YahooFinance":
        candles = get_stock_candles(instrument.symbol, "1h")
        if candles:
            return candles[-1]["close"]

    return None


def get_binance_candles(symbol, interval="1h", limit=100):
    """Fetch raw Binance candles. Return an empty list on API failure."""
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
            timeout=API_TIMEOUT_SECONDS,
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


def get_hyperliquid_candles(symbol, interval="1h", limit=100):
    """Fetch raw Hyperliquid candles and keep the requested last candles."""
    # Hyperliquid expects timestamps in milliseconds.
    end_time_ms = int(time.time() * 1000)

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": symbol,
            "interval": interval,
            "startTime": 0,
            "endTime": end_time_ms,
        },
    }

    try:
        response = requests.post(
            HYPERLIQUID_API_URL,
            json=payload,
            timeout=API_TIMEOUT_SECONDS,
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


def get_formatted_hyperliquid_candles(symbol, interval="1h", limit=100):
    """Convert Hyperliquid field names to the format used by the dashboard."""
    candles = get_hyperliquid_candles(symbol, interval=interval, limit=limit)

    formatted_candles = []

    for candle in candles:
        formatted_candle = {
            "open_time": candle["t"],
            "open": float(candle["o"]),
            "high": float(candle["h"]),
            "low": float(candle["l"]),
            "close": float(candle["c"]),
        }

        formatted_candles.append(formatted_candle)

    return formatted_candles


def get_formatted_binance_candles(symbol, interval="1h", limit=100):
    """Convert Binance list positions to named dashboard fields."""
    candles = get_binance_candles(symbol, interval=interval, limit=limit)

    formatted_candles = []

    for candle in candles:
        formatted_candle = {
            "open_time": candle[0],
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
        }

        formatted_candles.append(formatted_candle)

    return formatted_candles


def get_instrument_candles(instrument, interval="1h", limit=100):
    """Fetch, format, and validate candles from the saved data source."""
    if instrument.data_source == "YahooFinance":
        return get_stock_candles(instrument.symbol, interval)[-limit:]
    if instrument.data_source == "Binance":
        candles = get_formatted_binance_candles(
            instrument.symbol,
            interval=interval,
            limit=limit,
        )
    elif instrument.data_source == "Hyperliquid":
        candles = get_formatted_hyperliquid_candles(
            instrument.symbol,
            interval=interval,
            limit=limit,
        )
    else:
        return []

    return validate_candles(candles)


def get_simple_trend(candles):
    if not candles:
        return "No data"

    first_close = candles[0]["close"]
    last_close = candles[-1]["close"]

    if last_close > first_close:
        return "Uptrend"

    elif last_close < first_close:
        return "Downtrend"

    return "Sideways"


def calculate_sma(candles, period):
    if len(candles) < period:
        return None

    closes = []

    for candle in candles[-period:]:
        closes.append(candle["close"])

    return sum(closes) / period


def get_sma_analysis(candles):
    if len(candles) < 50:
        return None

    sma20 = calculate_sma(candles, 20)
    sma50 = calculate_sma(candles, 50)

    current_close = candles[-1]["close"]

    return {
        "sma20": sma20,
        "sma50": sma50,
        "price_above_sma20": current_close > sma20,
        "price_above_sma50": current_close > sma50,
    }


def calculate_rsi(candles, period=14):
    if len(candles) < period + 1:
        return None

    closes = [candle["close"] for candle in candles]

    changes = [
        closes[i] - closes[i - 1]
        for i in range(1, len(closes))
    ]

    gains = [max(change, 0) for change in changes]
    losses = [abs(min(change, 0)) for change in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        avg_gain = (
                           avg_gain * (period - 1) + gains[i]
                   ) / period

        avg_loss = (
                           avg_loss * (period - 1) + losses[i]
                   ) / period

    if avg_loss == 0:
        return 100 if avg_gain > 0 else 50

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


def get_rsi_analysis(candles):
    rsi = calculate_rsi(candles)

    if rsi is None:
        return None

    if rsi >= 70:
        condition = "Overbought"
    elif rsi <= 30:
        condition = "Oversold"
    elif rsi >= 50:
        condition = "Bullish Momentum"
    else:
        condition = "Bearish Momentum"

    return {
        "rsi": round(rsi, 2),
        "condition": condition,
    }


def get_timeframe_signal(trend, sma_analysis, rsi_analysis):
    score = 0
    factors = []

    # 1. Trend
    if trend == "Uptrend":
        score += 1
        factors.append("Trend bullish")
    elif trend == "Downtrend":
        score -= 1
        factors.append("Trend bearish")

    # 2. SMA
    if sma_analysis:
        if sma_analysis["price_above_sma20"]:
            score += 1
            factors.append("Price above SMA20")
        else:
            score -= 1
            factors.append("Price below SMA20")

        if sma_analysis["price_above_sma50"]:
            score += 1
            factors.append("Price above SMA50")
        else:
            score -= 1
            factors.append("Price below SMA50")

    # 3. RSI
    if rsi_analysis:
        rsi = rsi_analysis["rsi"]

        if rsi >= 55:
            score += 1
            factors.append("RSI bullish")
        elif rsi <= 45:
            score -= 1
            factors.append("RSI bearish")
        else:
            factors.append("RSI neutral")

    indicators_available = sum([
        trend in ["Uptrend", "Downtrend", "Sideways"],
        bool(sma_analysis),
        bool(rsi_analysis),
    ])

    if indicators_available < 2:
        return {
            "score": None,
            "signal": "Insufficient data",
            "factors": factors,
            "indicators_available": indicators_available,
        }

    if score >= 2:
        signal = "Bullish"
    elif score <= -2:
        signal = "Bearish"
    else:
        signal = "Neutral"

    return {
        "score": score,
        "signal": signal,
        "factors": factors,
        "indicators_available": indicators_available,
    }


def get_overall_signal(timeframe_signals):
    weights = {
        "1h": 1,
        "4h": 2,
        "1d": 3,
    }

    weighted_score = 0
    total_weight = 0

    for timeframe, weight in weights.items():
        analysis = timeframe_signals.get(timeframe)

        if not analysis or analysis.get("score") is None:
            continue

        weighted_score += analysis["score"] * weight
        total_weight += weight

    if total_weight == 0:
        return {
            "score": None,
            "signal": "No data",
            "timeframes_used": 0,
        }

    score = round(weighted_score / total_weight, 2)

    if score >= 1.5:
        signal = "Bullish"
    elif score <= -1.5:
        signal = "Bearish"
    else:
        signal = "Neutral"

    return {
        "score": score,
        "signal": signal,
        "timeframes_used": total_weight,
    }


def get_signal_consensus(timeframe_signals):
    valid_signals = [
        data["signal"]
        for data in timeframe_signals.values()
        if data and data.get("signal") in [
            "Bullish", "Bearish", "Neutral"
        ]
    ]

    bullish = valid_signals.count("Bullish")
    bearish = valid_signals.count("Bearish")
    neutral = valid_signals.count("Neutral")
    total = len(valid_signals)

    if total == 0:
        alignment = "No data"
    elif bullish == total or bearish == total:
        alignment = "Full agreement"
    elif bullish > bearish and bullish > neutral:
        alignment = "Bullish majority, some disagreement"
    elif bearish > bullish and bearish > neutral:
        alignment = "Bearish majority, some disagreement"
    elif bullish > 0 and bearish > 0:
        alignment = "Conflicting signals"
    else:
        alignment = "Mostly neutral"

    return {
        "alignment": alignment,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "timeframes_analyzed": total,
    }


def validate_candles(candles):
    if not isinstance(candles, list):
        return []

    valid_candles = []

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

        valid_candles.append({
            "open_time": open_time,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
        })

    valid_candles.sort(key=lambda candle: candle["open_time"])
    return valid_candles


def get_chart_data(candles):
    if not candles:
        return {
            "labels": [],
            "prices": [],
            "sma20": [],
            "sma50": [],
            "rsi": [],
        }

    closes = [candle["close"] for candle in candles]
    labels = [candle["open_time"] for candle in candles]

    sma20 = []
    sma50 = []

    for i in range(len(closes)):
        if i >= 19:
            sma20.append(sum(closes[i - 19:i + 1]) / 20)
        else:
            sma20.append(None)

        if i >= 49:
            sma50.append(sum(closes[i - 49:i + 1]) / 50)
        else:
            sma50.append(None)

    rsi_values = [None] * len(closes)
    period = 14

    if len(closes) > period:
        changes = [
            closes[i] - closes[i - 1]
            for i in range(1, len(closes))
        ]

        gains = [max(change, 0) for change in changes]
        losses = [abs(min(change, 0)) for change in changes]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        def calculate_rsi_value(gain, loss):
            if loss == 0:
                return 100 if gain > 0 else 50

            rs = gain / loss
            return 100 - (100 / (1 + rs))

        rsi_values[period] = calculate_rsi_value(
            avg_gain,
            avg_loss,
        )

        for i in range(period + 1, len(closes)):
            change_index = i - 1

            avg_gain = (
                               avg_gain * (period - 1) + gains[change_index]
                       ) / period

            avg_loss = (
                               avg_loss * (period - 1) + losses[change_index]
                       ) / period

            rsi_values[i] = calculate_rsi_value(
                avg_gain,
                avg_loss,
            )

    return {
        "labels": labels,
        "prices": closes,
        "sma20": sma20,
        "sma50": sma50,
        "rsi": [
            round(value, 2) if value is not None else None
            for value in rsi_values
        ],
    }
