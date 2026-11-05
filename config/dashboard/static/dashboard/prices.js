// Modulis keičia kortelių kainas ir perduoda tikras biržų OHLC žvakes grafikų moduliui.
// Atskira funkcijos sritis neleidžia kainų kintamiesiems susimaišyti su charts.js kintamaisiais.
(() => {
    const latestQuotes = {};
    const yahooErrors = {};
    const streams = {};
    const timeFormat = new Intl.DateTimeFormat(undefined, {
        month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
    let pricesInProgress = false;
    let priceRequest = null;
    let pageActive = true;

    // Grąžina šiuo metu puslapyje esančias korteles, taip pat po jų HTML pakeitimo.
    function getCards(source) {
        return Array.from(document.querySelectorAll(".instrument-card[data-source]"))
            .filter(card => !source || card.dataset.source === source);
    }

    // Patikrina, ar šiuo metu verta palaikyti tinklo ryšius.
    function canConnect() {
        return pageActive && !document.hidden && navigator.onLine;
    }

    // Formatuoja kainą; Binance poros kotiruojamos USDT, todėl ši valiuta nurodoma tiesiogiai.
    function formatQuote(quote, source) {
        if (source === "Binance") {
            return new Intl.NumberFormat(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 3})
                .format(quote.price) + " USDT";
        }
        return new Intl.NumberFormat(undefined, {
            style: "currency", currency: quote.currency, minimumFractionDigits: 2, maximumFractionDigits: 3
        }).format(quote.price);
    }

    // Pritaiko paskutinę kainą dabartinei kortelei ir parodo tikrą jos gavimo arba šaltinio laiką.
    function renderCard(card) {
        const id = card.dataset.instrumentId;
        const source = card.dataset.source;
        const quote = latestQuotes[id];
        if (quote) {
            card.querySelector("[data-live-price]").textContent = formatQuote(quote, source);
            card.querySelector("[data-price-time]").textContent = source === "YahooFinance"
                ? `Quote: ${timeFormat.format(quote.priceTime)} · Checked: ${timeFormat.format(quote.receivedAt)}`
                : `Received: ${timeFormat.format(quote.receivedAt)}`;
        }

        let status;
        if (!canConnect()) {
            status = navigator.onLine ? "Updates paused" : "Offline — showing last price";
        } else if (source === "YahooFinance") {
            status = yahooErrors[id] ? "Yahoo unavailable — showing last price"
                : quote ? "Yahoo · checked every 45s · may be delayed" : "Yahoo · checking price…";
        } else if (source === "Binance" || source === "Hyperliquid") {
            const stream = streams[source];
            const fresh = quote && Date.now() - quote.receivedAt < 30000;
            status = stream?.status === "Connected"
                ? fresh ? `Live · ${source}` : "Connected — waiting for price…"
                : stream?.status || "Connecting…";
        } else {
            status = "Saved price";
        }
        card.querySelector("[data-price-status]").textContent = status;
    }

    // Atmeta netinkamas ar atgal laike einančias kainas, o pokytį trumpai paryškina spalva.
    function updateQuote(card, quote) {
        if (!Number.isFinite(quote.price) || quote.price <= 0 || !Number.isFinite(quote.receivedAt)) {
            return;
        }
        const id = card.dataset.instrumentId;
        const previous = latestQuotes[id];
        if (previous && quote.priceTime < previous.priceTime) {
            return;
        }
        latestQuotes[id] = {...quote, source: card.dataset.source, symbol: card.dataset.symbol};
        renderCard(card);
        if (previous && quote.price !== previous.price) {
            const element = card.querySelector("[data-live-price]");
            element.classList.remove("price-up", "price-down");
            // Perskaičiavus išdėstymą ta pati animacija gali prasidėti dar kartą.
            void element.offsetWidth;
            element.classList.add(quote.price > previous.price ? "price-up" : "price-down");
        }
    }

    // Perskaito tikėtą konkretaus šaltinio žinutę; kitos žinutės, pavyzdžiui pong, ignoruojamos.
    function readStreamMessage(source, message) {
        const receivedAt = Date.now();
        if (source === "Binance" && message.data?.e === "24hrMiniTicker") {
            const data = message.data;
            if (!Number.isFinite(data.E)) {
                return;
            }
            getCards(source).filter(card => `${card.dataset.symbol.toUpperCase()}USDT` === data.s)
                .forEach(card => updateQuote(card, {
                    price: Number(data.c), priceTime: data.E, receivedAt, currency: "USD"
                }));
        } else if (source === "Hyperliquid" && message.channel === "allMids" && message.data?.mids) {
            // allMids laiko žymos neturi: laikas ekrane reiškia žinutės gavimą naršyklėje.
            getCards(source).forEach(card => updateQuote(card, {
                price: Number(message.data.mids[card.dataset.symbol]),
                priceTime: receivedAt, receivedAt, currency: "USD"
            }));
        } else if (source === "Binance" && message.data?.e === "kline") {
            const data = message.data;
            const candle = data.k;
            if (candle && Number.isFinite(data.E)) {
                getCards(source).filter(card => `${card.dataset.symbol.toUpperCase()}USDT` === data.s)
                    .forEach(card => publishCandle(card, candle.i, candle, data.E));
            }
        } else if (source === "Hyperliquid" && message.channel === "candle") {
            // Hyperliquid gali pateikti vieną žvakę arba pradinį žvakių sąrašą.
            const candles = Array.isArray(message.data) ? message.data : [message.data];
            candles.filter(candle => candle && typeof candle === "object").forEach(candle => {
                getCards(source).filter(card => card.dataset.symbol === candle.s)
                    .forEach(card => publishCandle(card, candle.i, candle, receivedAt));
            });
        }
    }

    // Sulygina laukų pavadinimus ir perduoda žvakę; galutinį OHLC tikrinimą atlieka charts.js.
    function publishCandle(card, interval, candle, updatedAt) {
        document.dispatchEvent(new CustomEvent("marketcandle", {detail: {
            id: card.dataset.instrumentId, source: card.dataset.source, symbol: card.dataset.symbol,
            interval, updatedAt,
            candle: {x: Number(candle.t), o: Number(candle.o), h: Number(candle.h), l: Number(candle.l), c: Number(candle.c)}
        }}));
    }

    // Prisijungia prie vieno šaltinio. Nutrūkęs ryšys atkuriamas vis didinant laukimą iki 30 sekundžių.
    function connectStream(source) {
        const stream = streams[source];
        if (!canConnect() || stream.socket || stream.retryTimer) {
            return;
        }
        stream.status = "Connecting…";
        stream.lastMessageAt = Date.now();
        try {
            const socket = new WebSocket(stream.url);
            stream.socket = socket;
            socket.onopen = () => {
                stream.status = "Connected";
                stream.lastMessageAt = Date.now();
                if (source === "Hyperliquid") {
                    socket.send(JSON.stringify({method: "subscribe", subscription: {type: "allMids"}}));
                    getCards(source).forEach(card => {
                        ["1h", "4h", "1d"].forEach(interval => {
                            socket.send(JSON.stringify({method: "subscribe", subscription: {
                                type: "candle", coin: card.dataset.symbol, interval
                            }}));
                        });
                    });
                }
                getCards(source).forEach(renderCard);
            };
            socket.onmessage = event => {
                stream.lastMessageAt = Date.now();
                stream.retries = 0;
                try {
                    readStreamMessage(source, JSON.parse(event.data));
                } catch (error) {
                    // Viena neatpažinta žinutė neturi nutraukti likusių kainų atnaujinimo.
                }
            };
            socket.onerror = () => socket.close();
            socket.onclose = () => {
                stream.socket = null;
                retryStream(source);
            };
        } catch (error) {
            retryStream(source);
        }
    }

    // Suplanuoja vieną pakartotinį bandymą; sena kaina lieka matoma su ryšio būsenos tekstu.
    function retryStream(source) {
        const stream = streams[source];
        stream.status = "Disconnected — retrying…";
        getCards(source).forEach(renderCard);
        if (canConnect() && !stream.retryTimer) {
            const delay = Math.min(30000, 1000 * 2 ** Math.min(stream.retries, 5));
            stream.retries += 1;
            stream.retryTimer = setTimeout(() => {
                stream.retryTimer = null;
                connectStream(source);
            }, delay);
        }
    }

    // Uždaro ryšį ir atšaukia bandymus, kai kortelė paslėpta arba pasikeičia instrumentų sąrašas.
    function stopStream(stream) {
        clearTimeout(stream.retryTimer);
        stream.retryTimer = null;
        if (stream.socket) {
            stream.socket.onclose = null;
            stream.socket.close();
            stream.socket = null;
        }
        stream.status = "Updates paused";
    }

    // Iš dabartinių kortelių sudaro prenumeratas: vienas Binance ir vienas Hyperliquid ryšys.
    function syncStreams() {
        // Naujesnė DB kaina gali pakeisti seną srauto kainą, jei ryšys ilgai neveikė.
        // Pakeitus instrumento simbolį ar šaltinį ankstesnė kaina taip pat nebenaudojama.
        getCards().forEach(card => {
            const quote = latestQuotes[card.dataset.instrumentId];
            if (quote && (quote.source !== card.dataset.source || quote.symbol !== card.dataset.symbol
                || quote.receivedAt < Date.parse(card.dataset.savedPriceTime))) {
                delete latestQuotes[card.dataset.instrumentId];
            }
        });
        ["Binance", "Hyperliquid"].forEach(source => {
            const symbols = [...new Set(getCards(source).map(card => card.dataset.symbol))].sort();
            const signature = symbols.join(",");
            if (streams[source] && streams[source].signature !== signature) {
                stopStream(streams[source]);
                delete streams[source];
            }
            if (!symbols.length) {
                return;
            }
            if (!streams[source]) {
                const names = symbols.flatMap(symbol => {
                    const pair = `${symbol.toLowerCase()}usdt`;
                    return [`${pair}@miniTicker`, ...["1h", "4h", "1d"].map(interval => `${pair}@kline_${interval}`)];
                }).join("/");
                streams[source] = {
                    signature, retries: 0, retryTimer: null, socket: null,
                    url: source === "Binance" ? `wss://data-stream.binance.vision:443/stream?streams=${names}`
                        : "wss://api.hyperliquid.xyz/ws"
                };
            }
            connectStream(source);
        });
        getCards().forEach(renderCard);
    }

    // Kas 45 sekundes prašo tik Yahoo kainų; API užklausą ir trumpą kešą tvarko Django.
    async function refreshStockPrices() {
        if (!canConnect() || pricesInProgress || !getCards("YahooFinance").length) {
            return;
        }
        pricesInProgress = true;
        priceRequest = new AbortController();
        const timeout = setTimeout(() => priceRequest.abort(), 20000);
        try {
            const response = await fetch(document.getElementById("dashboard").dataset.pricesUrl, {
                cache: "no-store", signal: priceRequest.signal
            });
            if (!response.ok) {
                throw new Error("Price request failed");
            }
            const data = await response.json();
            // Pirma pažymime visus kaip negautus, kad trūkstamas įrašas neatrodytų sėkmingas.
            getCards("YahooFinance").forEach(card => { yahooErrors[card.dataset.instrumentId] = true; });
            data.quotes.forEach(item => {
                const card = getCards("YahooFinance").find(card => card.dataset.instrumentId === String(item.id));
                const quote = item.quote;
                if (card && quote && Number.isFinite(quote.price_time) && Number.isFinite(quote.checked_at)
                    && Number.isFinite(quote.price) && quote.price > 0 && /^[A-Z]{3}$/.test(quote.currency)) {
                    yahooErrors[item.id] = false;
                    updateQuote(card, {
                        price: quote.price, priceTime: quote.price_time,
                        receivedAt: quote.checked_at, currency: quote.currency
                    });
                }
            });
        } catch (error) {
            getCards("YahooFinance").forEach(card => { yahooErrors[card.dataset.instrumentId] = true; });
        } finally {
            clearTimeout(timeout);
            priceRequest = null;
            pricesInProgress = false;
            getCards("YahooFinance").forEach(renderCard);
        }
    }

    // Sumažina tinklo naudojimą paslėpus puslapį, o grįžus atkuria ryšius ir patikrina Yahoo.
    function handleVisibility() {
        if (!canConnect()) {
            Object.values(streams).forEach(stopStream);
            priceRequest?.abort();
            getCards().forEach(renderCard);
        } else {
            syncStreams();
            refreshStockPrices();
        }
    }

    // Periodinis ping palaiko Hyperliquid ryšį; užstrigę ryšiai uždaromi ir atkuriami.
    setInterval(() => {
        if (!canConnect()) {
            return;
        }
        Object.entries(streams).forEach(([source, stream]) => {
            const socket = stream.socket;
            if (socket && Date.now() - stream.lastMessageAt > 45000) {
                socket.close();
            } else if (source === "Hyperliquid" && socket?.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({method: "ping"}));
            }
        });
        getCards().forEach(renderCard);
    }, 20000);
    setInterval(refreshStockPrices, 45000);
    document.addEventListener("dashboardrefresh", syncStreams);
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("online", handleVisibility);
    window.addEventListener("offline", handleVisibility);
    window.addEventListener("pagehide", () => { pageActive = false; handleVisibility(); });
    window.addEventListener("pageshow", () => { pageActive = true; handleVisibility(); });
    syncStreams();
    refreshStockPrices();
})();
