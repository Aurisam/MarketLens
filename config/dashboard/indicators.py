"""Techninių rodiklių ir signalų skaičiavimas iš jau patikrintų žvakių."""

TIMEFRAME_WEIGHTS = {"1h": 1, "4h": 2, "1d": 3}


def get_simple_trend(candles):
    """Nustato paprastą kryptį palygindama pirmos ir paskutinės žvakės uždarymo kainas."""
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
    """Apskaičiuoja paskutinių period uždarymo kainų vidurkį; trūkstant žvakių grąžina None."""
    if len(candles) < period:
        return None

    closes = []

    for candle in candles[-period:]:
        closes.append(candle["close"])

    return sum(closes) / period


def get_sma_analysis(candles):
    """Apskaičiuoja SMA20 bei SMA50 ir patikrina, ar paskutinė kaina yra virš jų."""
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


def calculate_rsi_series(candles, period=14):
    """Grąžina kiekvienos žvakės Wilder RSI; pradžioje palieka None, kol pakanka istorijos."""
    values = [None] * len(candles)
    if len(candles) <= period:
        return values

    average_gain = 0
    average_loss = 0
    for index in range(1, len(candles)):
        change = candles[index]["close"] - candles[index - 1]["close"]
        gain = max(change, 0)
        loss = max(-change, 0)

        # Pirmoms 14 permainų naudojamas paprastas vidurkis, vėliau – Wilder glodinimas.
        if index <= period:
            average_gain += gain / period
            average_loss += loss / period
        else:
            average_gain = (average_gain * (period - 1) + gain) / period
            average_loss = (average_loss * (period - 1) + loss) / period

        if index >= period:
            if average_loss == 0:
                values[index] = 100 if average_gain > 0 else 50
            else:
                strength = average_gain / average_loss
                values[index] = 100 - 100 / (1 + strength)

    return values


def calculate_rsi(candles, period=14):
    """Paskutinę RSI reikšmę paima iš tos pačios sekos, kuri naudojama grafike."""
    values = calculate_rsi_series(candles, period)
    return values[-1] if values else None


def get_rsi_analysis(candles):
    """Grąžina iki dviejų skaitmenų suapvalintą RSI ir jo reikšmės apibūdinimą."""
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
    """Sujungia krypties, SMA ir RSI balus į vieno intervalo signalą bei jo priežastis."""
    score = 0
    factors = []

    # Kylanti kryptis prideda vieną balą, krintanti atima; šoninė kryptis balo nekeičia.
    if trend == "Uptrend":
        score += 1
        factors.append("Uptrend: first-to-last close increased (+1)")
    elif trend == "Downtrend":
        score -= 1
        factors.append("Downtrend: first-to-last close decreased (-1)")
    elif trend == "Sideways":
        factors.append("Sideways: first and last close are equal (0)")

    # Kainos pozicija virš arba žemiau kiekvieno SMA prideda arba atima po vieną balą.
    if sma_analysis:
        if sma_analysis["price_above_sma20"]:
            score += 1
            factors.append("Price above SMA20 (+1)")
        else:
            score -= 1
            factors.append("Price at or below SMA20 (-1)")

        if sma_analysis["price_above_sma50"]:
            score += 1
            factors.append("Price above SMA50 (+1)")
        else:
            score -= 1
            factors.append("Price at or below SMA50 (-1)")

    # Signalo RSI ribos yra 55 ir 45; tai atskira taisyklė nuo 70/30 būsenų aprašymo.
    if rsi_analysis:
        rsi = rsi_analysis["rsi"]

        if rsi >= 55:
            score += 1
            factors.append("RSI at least 55 (+1)")
        elif rsi <= 45:
            score -= 1
            factors.append("RSI at most 45 (-1)")
        else:
            factors.append("RSI between 45 and 55 (0)")

    # Signalui reikia bent dviejų indikatorių grupių; SMA20 ir SMA50 čia laikomi viena grupe.
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
    """Apskaičiuoja bendrą signalą, ilgesnių intervalų balams suteikdama didesnį svorį."""
    # Dieninis signalas turi svorį 3, keturių valandų 2, valandinis 1.
    weighted_score = 0
    total_weight = 0
    timeframes_used = 0

    for timeframe, weight in TIMEFRAME_WEIGHTS.items():
        analysis = timeframe_signals.get(timeframe)

        if not analysis or analysis.get("score") is None:
            continue

        weighted_score += analysis["score"] * weight
        total_weight += weight
        timeframes_used += 1

    if total_weight == 0:
        return {
            "score": None,
            "signal": "No data",
            "timeframes_used": 0,
            "total_weight": 0,
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
        "timeframes_used": timeframes_used,
        "total_weight": total_weight,
    }


def get_signal_consensus(timeframe_signals):
    """Suskaičiuoja galiojančius intervalų signalus ir apibūdina jų tarpusavio sutapimą."""
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


def get_chart_data(candles):
    """Paruošia vienodo ilgio kainų, laiko, SMA ir RSI sąrašus grafikams."""
    if not candles:
        return {
            "labels": [],
            "prices": [],
            "opens": [],
            "highs": [],
            "lows": [],
            "sma20": [],
            "sma50": [],
            "rsi": [],
        }

    closes = [candle["close"] for candle in candles]
    labels = [candle["open_time"] for candle in candles]

    sma20 = []
    sma50 = []

    # Kiekvieno taško SMA skaičiuojamas tik iš tuo metu jau buvusių kainų.
    # Kol nesukaupta 20 ar 50 žvakių, None palieka tarpą grafiko linijoje.
    for i in range(len(closes)):
        if i >= 19:
            sma20.append(sum(closes[i - 19:i + 1]) / 20)
        else:
            sma20.append(None)

        if i >= 49:
            sma50.append(sum(closes[i - 49:i + 1]) / 50)
        else:
            sma50.append(None)

    rsi_values = calculate_rsi_series(candles)

    return {
        "labels": labels,
        "prices": closes,
        "opens": [candle["open"] for candle in candles],
        "highs": [candle["high"] for candle in candles],
        "lows": [candle["low"] for candle in candles],
        "sma20": sma20,
        "sma50": sma50,
        "rsi": [
            round(value, 2) if value is not None else None
            for value in rsi_values
        ],
    }
