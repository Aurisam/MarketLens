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

const chartInstances = {};

function getChartValues(canvas, timeframe, field) {
    const attributeName = `data-chart-${timeframe}-${field}`;
    return readNumbers(canvas.getAttribute(attributeName));
}

function createCharts(id, timeframe = "1h") {
    const priceCanvas = document.getElementById(`price-chart-${id}`);
    const rsiCanvas = document.getElementById(`rsi-chart-${id}`);

    if (!priceCanvas || !rsiCanvas) {
        return;
    }

    const labels = getChartValues(priceCanvas, timeframe, "labels");
    const prices = getChartValues(priceCanvas, timeframe, "prices");
    const sma20 = getChartValues(priceCanvas, timeframe, "sma20");
    const sma50 = getChartValues(priceCanvas, timeframe, "sma50");
    const rsiLabels = getChartValues(rsiCanvas, timeframe, "labels");
    const rsi = getChartValues(rsiCanvas, timeframe, "rsi");

    // All providers supply candle opening times as Unix milliseconds.
    function formatTime(timestamp) {
        const isoTime = new Date(timestamp).toISOString();
        return isoTime.slice(0, 10) + " " + isoTime.slice(11, 16);
    }
    const chartLabels = labels.map(formatTime);
    const rsiChartLabels = rsiLabels.map(formatTime);

    if (chartInstances[id]) {
        chartInstances[id].price.destroy();
        chartInstances[id].rsi.destroy();
    }

    chartInstances[id] = {
        price: new Chart(priceCanvas, {
            type: "line",
            data: {
                labels: chartLabels,
                datasets: [
                    {
                        label: "Price",
                        data: prices,
                        borderWidth: 2,
                        pointRadius: 0
                    },
                    {
                        label: "SMA 20",
                        data: sma20,
                        borderWidth: 1.5,
                        pointRadius: 0,
                        spanGaps: false
                    },
                    {
                        label: "SMA 50",
                        data: sma50,
                        borderWidth: 1.5,
                        pointRadius: 0,
                        spanGaps: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: "index"
                },
                scales: {
                    x: {
                        title: {display: true, text: "UTC"},
                        ticks: {
                            maxTicksLimit: 8
                        }
                    }
                }
            }
        }),

        rsi: new Chart(rsiCanvas, {
            type: "line",
            data: {
                labels: rsiChartLabels,
                datasets: [
                    {
                        label: "RSI 14",
                        data: rsi,
                        borderWidth: 2,
                        pointRadius: 0
                    },
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
                scales: {
                    y: {
                        min: 0,
                        max: 100
                    },
                    x: {
                        title: {display: true, text: "UTC"},
                        ticks: {
                            maxTicksLimit: 8
                        }
                    }
                }
            }
        })
    };
}

function changeTimeframe(id, timeframe, button) {
    createCharts(id, timeframe);

    const buttonGroup = button.parentElement;
    buttonGroup.querySelectorAll("button").forEach(timeframeButton => {
        timeframeButton.classList.remove("active");
    });
    button.classList.add("active");
}

document.querySelectorAll('[id^="price-chart-"]').forEach(canvas => {
    const id = canvas.id.replace("price-chart-", "");
    createCharts(id);
});
