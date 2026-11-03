const chartInstances = {};
const selectedTimeframes = {};
const localTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
const dateFormatter = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
});
let refreshInProgress = false;

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

function createCharts(id, timeframe = "1h") {
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
    const candles = times.map((time, index) => ({
        x: time,
        o: opens[index],
        h: highs[index],
        l: lows[index],
        c: prices[index]
    }));

    if (chartInstances[id]) {
        chartInstances[id].price.destroy();
        chartInstances[id].rsi.destroy();
    }

    chartInstances[id] = {
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
                interaction: {intersect: false, mode: "index"},
                plugins: {
                    tooltip: {
                        callbacks: {
                            title(items) {
                                return formatLocalTime(items[0].parsed.x);
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: "timeseries",
                        title: {display: true, text: localTimeZone},
                        ticks: {
                            source: "data",
                            maxTicksLimit: 8,
                            major: {enabled: false},
                            callback: formatLocalTime
                        }
                    },
                    y: {type: "linear"}
                }
            }
        }),
        rsi: new Chart(rsiCanvas, {
            type: "line",
            data: {
                labels: times.map(formatLocalTime),
                datasets: [
                    {label: "RSI 14", data: rsi, borderWidth: 2, pointRadius: 0},
                    {
                        label: "Overbought (70)",
                        data: rsi.map(() => 70),
                        borderDash: [5, 5],
                        pointRadius: 0
                    },
                    {
                        label: "Oversold (30)",
                        data: rsi.map(() => 30),
                        borderDash: [5, 5],
                        pointRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    y: {min: 0, max: 100},
                    x: {
                        title: {display: true, text: localTimeZone},
                        ticks: {maxTicksLimit: 8}
                    }
                }
            }
        })
    };
}

function changeTimeframe(id, timeframe, button) {
    selectedTimeframes[id] = timeframe;
    createCharts(id, timeframe);
    button.parentElement.querySelectorAll("button").forEach(timeframeButton => {
        timeframeButton.classList.toggle("active", timeframeButton === button);
    });
}

function initializeCards() {
    document.querySelectorAll("time[data-local-time]").forEach(element => {
        element.textContent = formatLocalTime(element.dataset.localTime);
    });

    document.querySelectorAll('[id^="price-chart-"]').forEach(canvas => {
        const id = canvas.id.replace("price-chart-", "");
        const timeframe = selectedTimeframes[id] || "1h";
        const card = canvas.closest(".instrument-card");
        const button = card.querySelector(`[data-timeframe="${timeframe}"]`);
        changeTimeframe(id, timeframe, button);
    });
}

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

        Object.keys(chartInstances).forEach(id => {
            chartInstances[id].price.destroy();
            chartInstances[id].rsi.destroy();
            delete chartInstances[id];
        });
        document.getElementById("instrument-cards").innerHTML = newCards.innerHTML;
        initializeCards();
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
