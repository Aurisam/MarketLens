"""Rinkos duomenų gavimas iš API ir žvakių pavertimas bendru formatu."""

import math
import time
from urllib.parse import quote

import requests
from django.core.cache import cache

# Viešas Binance rinkos duomenų adresas leidžia gauti kainas ir žvakes be API rakto.
BINANCE_API_URL = "https://data-api.binance.vision/api/v3"
HYPERLIQUID_API_URL = "https://api.hyperliquid.xyz/info"
API_TIMEOUT_SECONDS = 10
TIMEFRAMES = ("1h", "4h", "1d")


def get_instrument_details(symbol, source):
    """Patikrina tikrą platformos simbolį; Yahoo akcijos ir ETF tipą nustato iš atsakymo."""
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
    """Gauna naujausią Yahoo kainą ir jos laiką; trumpas kešas sumažina pakartotines užklausas."""
    # Kainoms naudojamas atskiras kešas nuo istorinių žvakių, kurios saugomos penkias minutes.
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
            # Išlaikome šaltinio vienetą, pvz., GBp reiškia pensus, o GBP – svarus.
            "currency": currency,
        }
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError, OverflowError):
        # Trumpam įsimenama ir nesėkmė, kad Yahoo sutrikimas nesukeltų užklausų lavinos.
        cache.set(cache_key, False, timeout=15)
        return None

    cache.set(cache_key, result, timeout=30)
    return result


def get_crypto_price(symbol):
    """Grąžina Binance kriptovaliutos kainą USDT; nepavykus užklausai grąžina None."""
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
    """Grąžina Hyperliquid vidurinę kainą; jos negavus grąžina None."""
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
    """Sujungia valandines žvakes į iki keturių valandų grupes toje pačioje prekybos sesijoje."""
    grouped = []
    hour = 60 * 60 * 1000
    previous_time = None
    for candle in hourly_candles:
        opened = candle["open_time"]
        # Ilgesnė nei valandos pertrauka pradeda naują sesiją, todėl skirtingų dienų žvakės nejungiamos.
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
    """Gauna akcijos ar ETF žvakes iš Yahoo Finance; 4h žvakes sudaro iš 1h duomenų."""
    if interval == "4h":
        return group_four_hour_candles(get_stock_candles(symbol, "1h", timeout=timeout))

    # Valandinėms ir dieninėms žvakėms prašome skirtingo ilgio istorijos.
    ranges = {"1h": "3mo", "1d": "6mo"}
    if interval not in ranges:
        return []

    # Trumpas serverio cache leidžia panaudoti tą patį Yahoo atsakymą 1h, 4h ir kainos gavimui.
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
        # Yahoo laiką pateikia sekundėmis, o šiame projekte visur naudojamos milisekundės.
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
                # Viena nepilna žvakė nepanaikina likusios gautos istorijos.
                continue
        candles = validate_candles(candles)
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        candles = []

    # Sėkmingi duomenys laikomi 5 minutes, nesėkmė tik 30 sekundžių, kad greičiau būtų bandoma dar kartą.
    cache.set(cache_key, candles, timeout=300 if candles else 30)
    return candles


def get_instrument_price(instrument):
    """Pagal instrumento duomenų šaltinį parenka kainos gavimo funkciją."""
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
    """Gauna neapdorotas Binance žvakes; API klaidos atveju grąžina tuščią sąrašą."""
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
    """Gauna Hyperliquid žvakes ir palieka ne daugiau kaip limit naujausių įrašų."""
    # Hyperliquid laukia Unix laiko milisekundėmis, todėl sekundes dauginame iš 1000.
    end_time_ms = int(time.time() * 1000)
    interval_ms = {"1h": 3600000, "4h": 14400000, "1d": 86400000}.get(interval)
    if interval_ms is None or limit <= 0:
        return []

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": symbol,
            "interval": interval,
            # Prašome tik reikalingo laikotarpio, o ne visos prieinamos istorijos nuo 1970 m.
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
    """Hyperliquid laukus paverčia bendru open_time, open, high, low ir close formatu."""
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
    """Binance sąrašo pozicijas paverčia tais pačiais įvardytais žvakės laukais."""
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
    """Parenka API pagal šaltinį ir grąžina vienodo formato patikrintas žvakes."""
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
    """Atmeta nepilnas ar nelogiškas žvakes ir likusias surikiuoja nuo seniausios."""
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

        # NaN, begalybė ir neigiamos ar nulinės kainos grafikams bei skaičiavimams netinka.
        if not all(math.isfinite(price) for price in prices):
            continue

        if min(prices) <= 0:
            continue

        # Open ir close turi patekti tarp low ir high; laikas negali būti neigiamas.
        if low_price > min(open_price, close_price):
            continue

        if high_price < max(open_price, close_price):
            continue

        if low_price > high_price:
            continue

        if open_time < 0:
            continue

        # Pasikartojus laikui paliekamas paskutinis įrašas; DB negaus dviejų vienodų raktų.
        valid_candles[open_time] = {
            "open_time": open_time,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
        }

    return sorted(valid_candles.values(), key=lambda candle: candle["open_time"])
