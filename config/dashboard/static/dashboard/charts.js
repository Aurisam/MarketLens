// Naršyklės grafikų būsena saugoma pagal instrumento ID, kad kortelės veiktų nepriklausomai.
const chartInstances = {};
const selectedTimeframes = {};
// Gyvos žvakės saugomos atskirai, kad jų neprarastume gavę senesnį DB HTML fragmentą.
const liveCandleData = {};
const pendingLiveRenders = {};
// Laiko juosta paimama iš vartotojo naršyklės, todėl konkreti šalis kode nenustatoma.
const localTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
const dateFormatter = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
});
const axisDateFormatter = new Intl.DateTimeFormat(undefined, {month: "2-digit", day: "2-digit"});
const axisTimeFormatter = new Intl.DateTimeFormat(undefined, {hour: "2-digit", minute: "2-digit"});
const priceFormatter = new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3
});
let refreshInProgress = false;
// Apsauga nuo ciklo: susiejus grafikus, vieno pakeitimas neturi be galo keisti kito.
let syncingCharts = false;

// Formatuoja kainą pagal naršyklės lokalę, visada palikdama 3 skaitmenis po kablelio.
function formatPrice(value) {
    return Number.isFinite(value) ? priceFormatter.format(value) : "—";
}

// Perkelia vieno instrumento matomą laiko intervalą iš kainos grafiko į RSI arba atvirkščiai.
function syncChartRange(id, sourceName) {
    const charts = chartInstances[id];
    if (!charts || syncingCharts) {
        return;
    }

    const source = charts[sourceName];
    const target = sourceName === "price" ? charts.rsi : charts.price;
    syncingCharts = true;
    try {
        target.zoomScale("x", {min: source.scales.x.min, max: source.scales.x.max}, "none");
    } finally {
        syncingCharts = false;
    }
}

// Ašies žymei grąžina dvi eilutes: vietinę datą ir vietinį laiką.
function formatAxisTime(timestamp) {
    const date = new Date(timestamp);
    return [axisDateFormatter.format(date), axisTimeFormatter.format(date)];
}

// Sukuria bendrus laiko ašies nustatymus; užrašai įjungiami tik apatiniame RSI grafike.
function getTimeScale(times, showLabels) {
    return {
        type: "timeseries",
        offset: true,
        min: times[0],
        max: times[times.length - 1],
        title: {display: showLabels, text: localTimeZone},
        border: {display: showLabels},
        grid: {drawTicks: showLabels},
        afterBuildTicks(scale) {
            // Abiejų grafikų vertikalios linijos remiasi tomis pačiomis žvakių laiko žymomis.
            const visibleTimes = times.filter(time => time >= scale.min && time <= scale.max);
            const tickCount = Math.max(2, Math.min(6, Math.floor(scale.maxWidth / 90)));
            const step = Math.max(1, Math.ceil(visibleTimes.length / tickCount));
            scale.ticks = visibleTimes.filter((time, index) => index % step === 0)
                .map(time => ({value: time}));
        },
        ticks: {
            display: showLabels,
            source: "data",
            autoSkip: false,
            maxRotation: 0,
            align: "inner",
            major: {enabled: false},
            callback: formatAxisTime
        }
    };
}

// Suvienodina Y ašių plotį, kad kainos ir RSI tinklelio linijos sutaptų.
function setAxisWidth(scale) {
    // Vienodas plotis abiem grafikams palieka tą pačią horizontalią braižymo sritį.
    scale.width = 84;
}

// Nustato priartinimo ir slinkimo valdymą bei susieja abiejų grafikų laiko intervalus.
function getZoomOptions(minRange, id, chartName) {
    return {
        limits: {x: {min: "original", max: "original", minRange}},
        pan: {
            enabled: true,
            mode: "x",
            modifierKey: "shift",
            onPan: () => syncChartRange(id, chartName)
        },
        zoom: {
            mode: "x",
            wheel: {enabled: true, modifierKey: "ctrl"},
            pinch: {enabled: true},
            onZoom: () => syncChartRange(id, chartName)
        }
    };
}

// Priartina kainos grafiką; jo onZoom automatiškai atnaujina ir RSI vaizdą.
function zoomCharts(id, factor) {
    chartInstances[id].price.zoom({x: factor}, "none");
}

// Grąžina abu instrumento grafikus į pradinį laiko intervalą.
function resetChartZoom(id) {
    const charts = chartInstances[id];
    [charts.price, charts.rsi].forEach(chart => {
        chart.resetZoom("none");
        // Gyvas srautas galėjo pridėti naują žvakę po pradinio grafiko sukūrimo.
        chart.options.scales.x.min = charts.times[0];
        chart.options.scales.x.max = charts.times.at(-1);
        chart.update("none");
    });
}

// Išsaugo pakeistą matomą intervalą; nepakeistam grafikui grąžina null.
function getChartRange(chart) {
    if (!chart.isZoomedOrPanned()) {
        return null;
    }
    return {min: chart.scales.x.min, max: chart.scales.x.max};
}

// Priderina grafiko tekstą, tinklelį ir užuominas prie pasirinktos šviesios arba tamsios temos.
function applyChartTheme(chart) {
    const isDark = document.documentElement.dataset.bsTheme === "dark";
    const textColor = isDark ? "#dee2e6" : "#495057";
    const gridColor = isDark ? "#495057" : "#dee2e6";
    chart.options.plugins.legend.labels.color = textColor;
    chart.options.plugins.title.color = textColor;
    chart.options.plugins.tooltip.backgroundColor = isDark ? "#f8f9fa" : "#212529";
    chart.options.plugins.tooltip.titleColor = isDark ? "#212529" : "#f8f9fa";
    chart.options.plugins.tooltip.bodyColor = isDark ? "#212529" : "#f8f9fa";
    Object.values(chart.options.scales).forEach(scale => {
        scale.ticks.color = textColor;
        scale.grid.color = gridColor;
        scale.border.color = gridColor;
        scale.title.color = textColor;
    });
    chart.update("none");
}

// Formatuoja laiko žymą naršyklės nustatyta laiko juosta ir lokalės formatu.
function formatLocalTime(timestamp) {
    return dateFormatter.format(new Date(timestamp));
}

// Paverčia kableliais atskirtas HTML reikšmes skaičiais; trūkstamas reikšmes paverčia null.
function readNumbers(value) {
    if (!value) {
        return [];
    }
    return value.split(",").map(item => {
        if (item === "None" || item === "") {
            return null;
        }
        return Number(item);
    });
}

// Iš canvas data atributų paima nurodyto intervalo ir lauko skaičių sąrašą.
function getChartValues(canvas, timeframe, field) {
    return readNumbers(canvas.getAttribute(`data-chart-${timeframe}-${field}`));
}

// Skaičiuoja SMA ir Wilder RSI kiekvienam taškui, kai žvakė keičiasi tiesioginiame sraute.
function calculateChartIndicators(candles) {
    const closes = candles.map(candle => candle.c);
    const sma20 = closes.map((value, index) => index >= 19
        ? closes.slice(index - 19, index + 1).reduce((sum, close) => sum + close, 0) / 20 : null);
    const sma50 = closes.map((value, index) => index >= 49
        ? closes.slice(index - 49, index + 1).reduce((sum, close) => sum + close, 0) / 50 : null);
    const rsi = closes.map(() => null);
    let gain = 0;
    let loss = 0;
    for (let index = 1; index < closes.length; index += 1) {
        const change = closes[index] - closes[index - 1];
        const up = Math.max(change, 0);
        const down = Math.max(-change, 0);
        if (index <= 14) {
            gain += up / 14;
            loss += down / 14;
        } else {
            gain = (gain * 13 + up) / 14;
            loss = (loss * 13 + down) / 14;
        }
        if (index >= 14) {
            rsi[index] = loss === 0 ? (gain > 0 ? 100 : 50) : 100 - 100 / (1 + gain / loss);
            rsi[index] = Math.round(rsi[index] * 100) / 100;
        }
    }
    return {sma20, sma50, rsi};
}

// Sujungia DB istoriją ir biržos OHLC žvakes pagal pradžios laiką, išlaikydama paskutines 100.
function getMergedCandles(id, timeframe, canvas) {
    const times = getChartValues(canvas, timeframe, "labels");
    const opens = getChartValues(canvas, timeframe, "opens");
    const highs = getChartValues(canvas, timeframe, "highs");
    const lows = getChartValues(canvas, timeframe, "lows");
    const closes = getChartValues(canvas, timeframe, "prices");
    const candles = new Map(times.map((time, index) => [time, {
        x: time, o: opens[index], h: highs[index], l: lows[index], c: closes[index]
    }]));
    const cache = liveCandleData[id];
    if (cache) {
        const card = canvas.closest(".instrument-card");
        if (cache.identity === `${card.dataset.source}:${card.dataset.symbol}`) {
            (cache.timeframes[timeframe] || []).forEach(item => candles.set(item.candle.x, item.candle));
        } else {
            delete liveCandleData[id];
        }
    }
    return [...candles.values()].sort((first, second) => first.x - second.x).slice(-100);
}

// Žyma atskiria gyvą grafiką nuo iš DB išsaugotų bendro signalo ir kortelės RSI reikšmių.
function updateCandleStatus(id) {
    const canvas = document.getElementById(`price-chart-${id}`);
    const status = canvas?.closest(".instrument-card").querySelector("[data-candle-status]");
    if (!status) {
        return;
    }
    const candles = liveCandleData[id]?.timeframes[selectedTimeframes[id] || "1h"];
    status.textContent = candles?.length
        ? `Live candles, SMA and RSI · ${formatLocalTime(candles.at(-1).updatedAt)}. Saved signal analysis is shown above.`
        : "Saved candles and indicators. Waiting for the next data update.";
}

// Pakeičia aktyvaus grafiko duomenis jo neperkurdama ir išlaiko vartotojo pasirinktą priartinimą.
function updateLiveChart(id) {
    const charts = chartInstances[id];
    const canvas = document.getElementById(`price-chart-${id}`);
    if (!charts || !canvas) {
        return;
    }
    if (!liveCandleData[id]?.timeframes[charts.timeframe]) {
        return;
    }
    const candles = getMergedCandles(id, charts.timeframe, canvas);
    if (!candles.length) {
        return;
    }
    const indicators = calculateChartIndicators(candles);
    const zoomed = charts.price.isZoomedOrPanned() || charts.rsi.isZoomedOrPanned();
    // Ašies callback naudoja tą patį times masyvą, todėl keičiame jo turinį, o ne nuorodą.
    charts.times.splice(0, charts.times.length, ...candles.map(candle => candle.x));
    charts.price.data.datasets[0].data = candles;
    charts.price.data.datasets[1].data = charts.times.map((time, index) => ({x: time, y: indicators.sma20[index]}));
    charts.price.data.datasets[2].data = charts.times.map((time, index) => ({x: time, y: indicators.sma50[index]}));
    charts.rsi.data.datasets[0].data = charts.times.map((time, index) => ({x: time, y: indicators.rsi[index]}));
    charts.rsi.data.datasets[1].data = charts.times.map(time => ({x: time, y: 70}));
    charts.rsi.data.datasets[2].data = charts.times.map(time => ({x: time, y: 30}));
    [charts.price, charts.rsi].forEach(chart => {
        chart.options.plugins.zoom.limits.x.min = charts.times[0];
        chart.options.plugins.zoom.limits.x.max = charts.times.at(-1);
        if (!zoomed) {
            chart.options.scales.x.min = charts.times[0];
            chart.options.scales.x.max = charts.times.at(-1);
        }
        chart.update("none");
    });
    updateCandleStatus(id);
}

// Priima tik tikrą biržos OHLC žvakę; vien iš naujos kainos open/high/low neišgalvojami.
function receiveLiveCandle(detail) {
    const {id, source, symbol, interval, candle, updatedAt} = detail;
    const canvas = document.getElementById(`price-chart-${id}`);
    const card = canvas?.closest(".instrument-card");
    if (!card || card.dataset.source !== source || card.dataset.symbol !== symbol
        || !["Binance", "Hyperliquid"].includes(source) || !["1h", "4h", "1d"].includes(interval)) {
        return;
    }
    const values = [candle.o, candle.h, candle.l, candle.c];
    if (!values.every(value => Number.isFinite(value) && value > 0)
        || !Number.isFinite(candle.x) || candle.x < 0 || candle.x > Date.now() + 60000
        || !Number.isFinite(updatedAt) || candle.l > Math.min(candle.o, candle.c)
        || candle.h < Math.max(candle.o, candle.c)) {
        return;
    }
    const identity = `${source}:${symbol}`;
    if (liveCandleData[id]?.identity !== identity) {
        liveCandleData[id] = {identity, timeframes: {}};
    }
    const timeframes = liveCandleData[id].timeframes;
    const saved = timeframes[interval] || [];
    const previous = saved.find(item => item.candle.x === candle.x);
    if (previous && previous.updatedAt > updatedAt) {
        return;
    }
    timeframes[interval] = [...saved.filter(item => item.candle.x !== candle.x), {candle, updatedAt}]
        .sort((first, second) => first.candle.x - second.candle.x).slice(-100);
    // Kelių intervalų žinutės gali ateiti kartu; aktyvus grafikas atnaujinamas vieną kartą per 250 ms.
    if (!pendingLiveRenders[id]) {
        pendingLiveRenders[id] = setTimeout(() => {
            delete pendingLiveRenders[id];
            updateLiveChart(id);
        }, 250);
    }
}

// Sukuria instrumento žvakių bei RSI grafikus ir, jei reikia, atkuria ankstesnį priartinimą.
function createCharts(id, timeframe = "1h", savedView = null) {
    const priceCanvas = document.getElementById(`price-chart-${id}`);
    const rsiCanvas = document.getElementById(`rsi-chart-${id}`);
    if (!priceCanvas || !rsiCanvas) {
        return;
    }

    const candles = getMergedCandles(id, timeframe, priceCanvas);
    const times = candles.map(candle => candle.x);
    const indicators = liveCandleData[id]?.timeframes[timeframe]
        ? calculateChartIndicators(candles) : {
            sma20: getChartValues(priceCanvas, timeframe, "sma20"),
            sma50: getChartValues(priceCanvas, timeframe, "sma50"),
            rsi: getChartValues(rsiCanvas, timeframe, "rsi")
        };
    const {sma20, sma50, rsi} = indicators;

    // Neleidžiame priartinti labiau nei maždaug iki dviejų intervalų pločio.
    const minRange = times.length > 1 ? (times[1] - times[0]) * 2 : 1;

    // Prieš panaudodami tuos pačius canvas elementus sunaikiname ankstesnius Chart objektus.
    if (chartInstances[id]) {
        chartInstances[id].price.destroy();
        chartInstances[id].rsi.destroy();
    }

    chartInstances[id] = {
        times, timeframe,
        // Viršutinis grafikas: OHLC žvakės su SMA20 ir SMA50 linijomis.
        price: new Chart(priceCanvas, {
            type: "candlestick",
            data: {
                datasets: [
                    {label: "Price", data: candles},
                    {
                        type: "line",
                        label: "SMA 20",
                        data: times.map((time, index) => ({x: time, y: sma20[index]})),
                        borderColor: "#2563eb",
                        borderWidth: 1.5,
                        pointRadius: 0,
                        spanGaps: false
                    },
                    {
                        type: "line",
                        label: "SMA 50",
                        data: times.map((time, index) => ({x: time, y: sma50[index]})),
                        borderColor: "#d97706",
                        borderWidth: 1.5,
                        pointRadius: 0,
                        spanGaps: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                layout: {padding: {right: 8}},
                // Užuomina rodoma tik pataikius ant žvakės, o ne bet kur toje pačioje X pozicijoje.
                interaction: {intersect: true, mode: "point"},
                plugins: {
                    legend: {
                        labels: {
                            // Paslepiame žvakių „Price“ legendą, bet paliekame SMA įjungimo mygtukus.
                            filter: item => item.datasetIndex !== 0
                        }
                    },
                    zoom: getZoomOptions(minRange, id, "price"),
                    tooltip: {
                        mode: "point",
                        intersect: true,
                        // SMA taškai neįtraukiami: užuominoje pateikiamos tik žvakės OHLC reikšmės.
                        filter: item => item.datasetIndex === 0,
                        callbacks: {
                            title(items) {
                                return formatLocalTime(items[0].parsed.x);
                            },
                            label(context) {
                                const candle = context.raw;
                                return [
                                    "Open: " + formatPrice(candle.o),
                                    "High: " + formatPrice(candle.h),
                                    "Low: " + formatPrice(candle.l),
                                    "Close: " + formatPrice(candle.c)
                                ];
                            }
                        }
                    }
                },
                scales: {
                    x: getTimeScale(times, false),
                    y: {type: "linear", afterFit: setAxisWidth}
                }
            }
        }),
        // Apatinis grafikas: RSI skalėje 0–100 ir pagalbinės 70 bei 30 ribos.
        rsi: new Chart(rsiCanvas, {
            type: "line",
            data: {
                datasets: [
                    {label: "RSI 14", data: times.map((time, index) => ({x: time, y: rsi[index]})), borderWidth: 2, pointRadius: 0},
                    {
                        label: "Overbought (70)",
                        data: times.map(time => ({x: time, y: 70})),
                        borderDash: [5, 5],
                        pointRadius: 0
                    },
                    {
                        label: "Oversold (30)",
                        data: times.map(time => ({x: time, y: 30})),
                        borderDash: [5, 5],
                        pointRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                    legend: {display: false},
                    title: {display: true, text: "RSI (14)", align: "start", padding: 4},
                    zoom: getZoomOptions(minRange, id, "rsi"),
                    tooltip: {
                        callbacks: {
                            title(items) {
                                return formatLocalTime(items[0].parsed.x);
                            }
                        }
                    }
                },
                layout: {padding: {right: 8}},
                scales: {
                    y: {min: 0, max: 100, afterFit: setAxisWidth},
                    x: getTimeScale(times, true)
                }
            }
        })
    };

    applyChartTheme(chartInstances[id].price);
    applyChartTheme(chartInstances[id].rsi);
    // Po automatinio atnaujinimo atkuriamas intervalas; susiejimas tokį pat pritaiko ir RSI.
    if (savedView) {
        const range = savedView.price || savedView.rsi;
        if (range) {
            chartInstances[id].price.zoomScale("x", range, "none");
        }
    }
}

// Įsimena pasirinktą intervalą, perkuria grafikus ir pažymi aktyvų mygtuką.
function changeTimeframe(id, timeframe, button, savedView = null) {
    selectedTimeframes[id] = timeframe;
    createCharts(id, timeframe, savedView);
    button.parentElement.querySelectorAll("button").forEach(timeframeButton => {
        timeframeButton.classList.toggle("active", timeframeButton === button);
    });
    updateCandleStatus(id);
}

// Paruošia kortelių vietinį laiką bei grafikus pirmą kartą arba atnaujinus HTML.
function initializeCards(savedViews = {}) {
    document.querySelectorAll("time[data-local-time]").forEach(element => {
        element.textContent = formatLocalTime(element.dataset.localTime);
    });

    document.querySelectorAll('[id^="price-chart-"]').forEach(canvas => {
        const id = canvas.id.replace("price-chart-", "");
        const timeframe = selectedTimeframes[id] || "1h";
        const card = canvas.closest(".instrument-card");
        const button = card.querySelector(`[data-timeframe="${timeframe}"]`);
        changeTimeframe(id, timeframe, button, savedViews[id]);
    });
}

// Gauna naują kortelių HTML iš Django, išlaikydama pasirinktus intervalus ir priartinimą.
async function refreshDashboard() {
    // Nepradedame lygiagrečios užklausos ir netikriname duomenų, kol kortelė naršyklėje paslėpta.
    if (refreshInProgress || document.hidden) {
        return;
    }

    refreshInProgress = true;
    const status = document.getElementById("refresh-status");
    // Užklausa nutraukiama po 15 sekundžių, kad lėtas atsakymas neužblokuotų vėlesnių bandymų.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    status.textContent = "Checking for updates...";

    try {
        const dashboard = document.getElementById("dashboard");
        const response = await fetch(dashboard.dataset.refreshUrl, {
            cache: "no-store",
            signal: controller.signal
        });
        if (!response.ok) {
            throw new Error("Dashboard request failed.");
        }

        // Pirma patikriname gautą HTML; blogo atsakymo atveju esamos kortelės lieka ekrane.
        const html = await response.text();
        const page = new DOMParser().parseFromString(html, "text/html");
        const newCards = page.getElementById("instrument-cards");
        if (!newCards) {
            throw new Error("Dashboard response is missing cards.");
        }

        // Prieš pakeisdami DOM išsaugome vaizdą ir atlaisviname senų grafikų išteklius.
        const savedViews = {};
        document.dispatchEvent(new Event("dashboardbeforerefresh"));
        Object.keys(chartInstances).forEach(id => {
            savedViews[id] = {
                price: getChartRange(chartInstances[id].price),
                rsi: getChartRange(chartInstances[id].rsi)
            };
            chartInstances[id].price.destroy();
            chartInstances[id].rsi.destroy();
            delete chartInstances[id];
        });
        document.getElementById("instrument-cards").innerHTML = newCards.innerHTML;
        initializeCards(savedViews);
        // Kainų modulis atkuria naujausias srauto kainas, kad DB HTML jų nepakeistų senesnėmis.
        document.dispatchEvent(new Event("dashboardrefresh"));
        status.textContent = `Checked: ${formatLocalTime(Date.now())}. Auto refresh enabled.`;
    } catch (error) {
        status.textContent = "Auto refresh failed. Retrying in one minute.";
    } finally {
        clearTimeout(timeout);
        refreshInProgress = false;
    }
}

// Pirmas atvaizdavimas ir periodinis DB duomenų tikrinimas kas 60 sekundžių.
// Tai skaito Django išsaugotus duomenis; rinkos API atskirai kviečia atnaujinimo komanda.
document.getElementById("time-zone").textContent = localTimeZone;
initializeCards();
setInterval(refreshDashboard, 60000);
// Grįžus į kortelę duomenys patikrinami iškart, nelaukiant kito minutės intervalo.
document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
        refreshDashboard();
    }
});

// Pakeitus temą perdažomi esami grafikai, todėl neprarandamas jų priartinimas.
document.addEventListener("themechange", () => {
    Object.values(chartInstances).forEach(charts => {
        applyChartTheme(charts.price);
        applyChartTheme(charts.rsi);
    });
});

document.addEventListener("marketcandle", event => receiveLiveCandle(event.detail));

// Filtras gali parodyti anksčiau paslėptą kortelę, todėl jos grafikams perskaičiuojamas dydis.
document.addEventListener("dashboardfilterchange", () => {
    Object.entries(chartInstances).forEach(([id, charts]) => {
        const item = document.getElementById(`price-chart-${id}`).closest("[data-instrument-item]");
        if (item && !item.hidden) {
            charts.price.resize();
            charts.rsi.resize();
        }
    });
});
