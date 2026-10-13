import requests, time


def get_crypto_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
    response = requests.get(url)
    data = response.json()
    return data['price']


def get_hyperliquid_price(symbol):
    url = "https://api.hyperliquid.xyz/info"
    payload = {"type": 'allMids',
               "dex": "",
               }
    response = requests.post(url,
                             json=payload,
                             headers={"Content-Type": "application/json"},
                             timeout=10,
                             )

    data = response.json()
    return data[symbol]


def get_instrument_price(instrument):
    if instrument.data_source == "Hyperliquid":
        return get_hyperliquid_price(instrument.symbol)

    elif instrument.data_source == "Binance":
        return get_crypto_price(instrument.symbol)

    return None


def get_binance_candles(symbol, interval="1h", limit=100):
    url = "https://api.binance.com/api/v3/klines"

    params = {
        "symbol": f"{symbol}USDT",
        "interval": interval,
        "limit": limit,
    }

    response = requests.get(
        url,
        params=params,
        timeout=10,
    )

    data = response.json()
    return data


def get_hyperliquid_candles(symbol, interval="1h", limit=100):
    url = "https://api.hyperliquid.xyz/info"

    end_time = int(time.time() * 1000)

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": symbol,
            "interval": interval,
            "startTime": 0,
            "endTime": end_time,
        }
    }

    response = requests.post(
        url,
        json=payload,
        timeout=10,
    )

    data = response.json()

    return data[-limit:]


def get_formatted_hyperliquid_candles(
        symbol,
        interval="1h",
        limit=100):

    candles = get_hyperliquid_candles(
        symbol,
        interval,
        limit
    )

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


def get_formatted_binance_candles(symbol,
                                  interval="1h",
                                  limit=100):

    candles = get_binance_candles(
        symbol,
        interval,
        limit
    )

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


def get_instrument_candles(
    instrument,
    interval="1h",
    limit=100
):
    if instrument.data_source == "Binance":
        return get_formatted_binance_candles(
            instrument.symbol,
            interval=interval,
            limit=limit
        )

    elif instrument.data_source == "Hyperliquid":
        return get_formatted_hyperliquid_candles(
            instrument.symbol,
            interval=interval,
            limit=limit
        )

    return []


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


def get_multi_timeframe_trends(instrument):
    timeframes = ["1h", "4h", "1d"]

    trends = {}

    for timeframe in timeframes:
        candles = get_instrument_candles(
            instrument,
            interval=timeframe
        )

        trends[timeframe] = get_simple_trend(candles)

    return trends

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

def get_multi_timeframe_sma(instrument):
    timeframes = ["1h", "4h", "1d"]

    sma_data = {}

    for timeframe in timeframes:
        candles = get_instrument_candles(
            instrument,
            interval=timeframe,
            limit=100
        )

        sma_data[timeframe] = get_sma_analysis(candles)

    return sma_data

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

def get_multi_timeframe_rsi(instrument):
    timeframes = ["1h", "4h", "1d"]
    rsi_data = {}

    for timeframe in timeframes:
        candles = get_instrument_candles(
            instrument,
            interval=timeframe,
            limit=100,
        )

        rsi_data[timeframe] = get_rsi_analysis(candles)

    return rsi_data

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
