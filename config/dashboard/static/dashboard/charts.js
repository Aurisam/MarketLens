// Naršyklės grafikų būsena saugoma pagal instrumento ID, kad kortelės veiktų nepriklausomai.
const chartInstances = {};
const selectedTimeframes = {};
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
    chartInstances[id].price.resetZoom("none");
    chartInstances[id].rsi.resetZoom("none");
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

// Sukuria instrumento žvakių bei RSI grafikus ir, jei reikia, atkuria ankstesnį priartinimą.
function createCharts(id, timeframe = "1h", savedView = null) {
    const priceCanvas = document.getElementById(`price-chart-${id}`);
    const rsiCanvas = document.getElementById(`rsi-chart-${id}`);
    if (!priceCanvas || !rsiCanvas) {
        return;
    }

    const times = getChartValues(priceCanvas, timeframe, "labels");
    const prices = getChartValues(priceCanvas, timeframe, "prices");
    const opens = getChartValues(priceCanvas, timeframe, "opens");
    const highs = getChartValues(priceCanvas, timeframe, "highs");
    const lows = getChartValues(priceCanvas, timeframe, "lows");
    const sma20 = getChartValues(priceCanvas, timeframe, "sma20");
    const sma50 = getChartValues(priceCanvas, timeframe, "sma50");
    const rsi = getChartValues(rsiCanvas, timeframe, "rsi");
    // Finansinių grafikų biblioteka tikisi x (laikas) ir o/h/l/c (žvakės kainos) laukų.
    const candles = times.map((time, index) => ({
        x: time,
        o: opens[index],
        h: highs[index],
        l: lows[index],
        c: prices[index]
    }));

    // Neleidžiame priartinti labiau nei maždaug iki dviejų intervalų pločio.
    const minRange = times.length > 1 ? (times[1] - times[0]) * 2 : 1;

    // Prieš panaudodami tuos pačius canvas elementus sunaikiname ankstesnius Chart objektus.
    if (chartInstances[id]) {
        chartInstances[id].price.destroy();
        chartInstances[id].rsi.destroy();
    }

    chartInstances[id] = {
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
