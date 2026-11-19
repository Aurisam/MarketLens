// Charts, live candles and periodic dashboard refreshes.
const chartInstances = {};
const selectedTimeframes = {};
const liveCandleData = {};
const pendingLiveRenders = {};
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
let syncingCharts = false;

function formatPrice(value) {
    return Number.isFinite(value) ? priceFormatter.format(value) : "—";
}

// Keep the price and RSI time ranges synchronized.
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

function formatAxisTime(timestamp) {
    const date = new Date(timestamp);
    return [axisDateFormatter.format(date), axisTimeFormatter.format(date)];
}

// Share candle timestamps; show time labels only below the RSI chart.
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

// Match axis widths so the price and RSI plots align.
function setAxisWidth(scale) {
    scale.width = 84;
}

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

function zoomCharts(id, factor) {
    chartInstances[id].price.zoom({x: factor}, "none");
}

function resetChartZoom(id) {
    const charts = chartInstances[id];
    [charts.price, charts.rsi].forEach(chart => {
        chart.resetZoom("none");
        chart.options.scales.x.min = charts.times[0];
        chart.options.scales.x.max = charts.times.at(-1);
        chart.update("none");
    });
}

function getChartRange(chart) {
    if (!chart.isZoomedOrPanned()) {
        return null;
    }
    return {min: chart.scales.x.min, max: chart.scales.x.max};
}

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

function formatLocalTime(timestamp) {
    return dateFormatter.format(new Date(timestamp));
}

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

function getChartValues(canvas, timeframe, field) {
    return readNumbers(canvas.getAttribute(`data-chart-${timeframe}-${field}`));
}

function calculateMovingAverages(closes, period) {
    const averages = [];
    for (let index = 0; index < closes.length; index += 1) {
        if (index + 1 < period) {
            averages.push(null);
            continue;
        }
        let sum = 0;
        for (let position = index - period + 1; position <= index; position += 1) {
            sum += closes[position];
        }
        averages.push(sum / period);
    }
    return averages;
}

// Calculate SMA and Wilder RSI for live candles.
function calculateChartIndicators(candles) {
    const closes = candles.map(candle => candle.c);
    const sma20 = calculateMovingAverages(closes, 20);
    const sma50 = calculateMovingAverages(closes, 50);
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
            if (loss === 0) {
                rsi[index] = gain > 0 ? 100 : 50;
            } else {
                rsi[index] = 100 - 100 / (1 + gain / loss);
            }
            rsi[index] = Math.round(rsi[index] * 100) / 100;
        }
    }
    return {sma20, sma50, rsi};
}

// Merge saved and live candles by opening time, keeping the latest 100.
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

// Update live data without recreating charts or losing zoom.
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
    // Mutate the array in place: axis callbacks retain this reference.
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
}

// Validate exchange OHLC data before updating the live cache.
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
    if (!pendingLiveRenders[id]) {
        pendingLiveRenders[id] = setTimeout(() => {
            delete pendingLiveRenders[id];
            updateLiveChart(id);
        }, 250);
    }
}

// Create the price and RSI charts and restore the saved view.
function createCharts(id, timeframe = "1h", savedView = null) {
    const priceCanvas = document.getElementById(`price-chart-${id}`);
    const rsiCanvas = document.getElementById(`rsi-chart-${id}`);
    if (!priceCanvas || !rsiCanvas) {
        return;
    }

    const candles = getMergedCandles(id, timeframe, priceCanvas);
    const times = candles.map(candle => candle.x);
    let indicators;
    if (liveCandleData[id]?.timeframes[timeframe]) {
        indicators = calculateChartIndicators(candles);
    } else {
        indicators = {
            sma20: getChartValues(priceCanvas, timeframe, "sma20"),
            sma50: getChartValues(priceCanvas, timeframe, "sma50"),
            rsi: getChartValues(rsiCanvas, timeframe, "rsi")
        };
    }
    const {sma20, sma50, rsi} = indicators;

    const minRange = times.length > 1 ? (times[1] - times[0]) * 2 : 1;

    if (chartInstances[id]) {
        chartInstances[id].price.destroy();
        chartInstances[id].rsi.destroy();
    }

    chartInstances[id] = {
        times, timeframe,
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
                interaction: {intersect: true, mode: "point"},
                plugins: {
                    legend: {
                        labels: {
                            filter: item => item.datasetIndex !== 0
                        }
                    },
                    zoom: getZoomOptions(minRange, id, "price"),
                    tooltip: {
                        mode: "point",
                        intersect: true,
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
    if (savedView) {
        const range = savedView.price || savedView.rsi;
        if (range) {
            chartInstances[id].price.zoomScale("x", range, "none");
        }
    }
}

function changeTimeframe(id, timeframe, button, savedView = null) {
    selectedTimeframes[id] = timeframe;
    createCharts(id, timeframe, savedView);
    button.parentElement.querySelectorAll("button").forEach(timeframeButton => {
        timeframeButton.classList.toggle("active", timeframeButton === button);
    });
}

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

// Refresh card HTML while preserving timeframes and zoom.
async function refreshDashboard() {
    if (refreshInProgress || document.hidden) {
        return;
    }

    refreshInProgress = true;
    const status = document.getElementById("refresh-status");
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

        const html = await response.text();
        const page = new DOMParser().parseFromString(html, "text/html");
        const newCards = page.getElementById("instrument-cards");
        if (!newCards) {
            throw new Error("Dashboard response is missing cards.");
        }

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
        document.dispatchEvent(new Event("dashboardrefresh"));
        status.textContent = `Checked: ${formatLocalTime(Date.now())}. Auto refresh enabled.`;
    } catch (error) {
        status.textContent = "Auto refresh failed. Retrying in one minute.";
    } finally {
        clearTimeout(timeout);
        refreshInProgress = false;
    }
}

document.getElementById("time-zone").textContent = localTimeZone;
initializeCards();
setInterval(refreshDashboard, 60000);
document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
        refreshDashboard();
    }
});

document.addEventListener("themechange", () => {
    Object.values(chartInstances).forEach(charts => {
        applyChartTheme(charts.price);
        applyChartTheme(charts.rsi);
    });
});

document.addEventListener("marketcandle", event => receiveLiveCandle(event.detail));

document.addEventListener("dashboardfilterchange", () => {
    Object.entries(chartInstances).forEach(([id, charts]) => {
        const item = document.getElementById(`price-chart-${id}`).closest("[data-instrument-item]");
        if (item && !item.hidden) {
            charts.price.resize();
            charts.rsi.resize();
        }
    });
});
