// Paleidimas: node tests/charts.test.mjs. Chart.js pakaitalas tikrina duomenų ir priartinimo būseną.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(new URL("../config/dashboard/static/dashboard/charts.js", import.meta.url), "utf8");
const hour = 3600000;
const start = Math.floor(Date.now() / hour) * hour - 60 * hour;
const last = start + 59 * hour;
const listeners = {};
const dispatched = [];
const created = [];
const buttons = {};
const status = {};
const wrapper = {hidden: false};
for (const timeframe of ["1h", "4h", "1d"]) {
    buttons[timeframe] = {classList: {toggle(name, active) { this.active = active; }}};
}
const group = {querySelectorAll: () => Object.values(buttons)};
Object.values(buttons).forEach(button => { button.parentElement = group; });
const card = {
    dataset: {source: "Binance", symbol: "BTC"},
    querySelector: selector => selector === "[data-candle-status]" ? status : buttons[selector.match(/"(.+)"/)[1]],
};
const canvas = {
    id: "price-chart-7",
    closest: selector => selector === "[data-instrument-item]" ? wrapper : card,
    getAttribute(name) {
        if (name.endsWith("labels")) return Array.from({length: 60}, (_, index) => start + index * hour).join(",");
        if (name.endsWith("sma20") || name.endsWith("sma50") || name.endsWith("rsi")) return "";
        const offset = name.endsWith("highs") ? 1 : name.endsWith("lows") ? -0.5 : 0;
        return Array.from({length: 60}, (_, index) => index + 1 + offset).join(",");
    },
};
const elements = {
    "price-chart-7": canvas, "rsi-chart-7": canvas, "time-zone": {}, "refresh-status": {},
    dashboard: {dataset: {refreshUrl: "/data/"}}, "instrument-cards": {},
};

// Chart pakaitalas imituoja tik pasirinktą X intervalą ir viešus update/zoom/resize metodus.
function FakeChart(target, config) {
    this.config = config;
    this.data = config.data;
    this.options = config.options;
    this.options.plugins.legend ??= {};
    this.options.plugins.legend.labels ??= {};
    this.options.plugins.title ??= {};
    for (const scale of Object.values(this.options.scales)) {
        scale.grid ??= {}; scale.ticks ??= {}; scale.border ??= {}; scale.title ??= {};
    }
    this.scales = {x: {min: config.options.scales.x.min, max: config.options.scales.x.max}};
    this.zoomed = false;
    this.isZoomedOrPanned = () => this.zoomed;
    this.update = () => { this.scales.x = {min: this.options.scales.x.min, max: this.options.scales.x.max}; };
    this.zoomScale = (axis, range) => {
        this.zoomed = true;
        Object.assign(this.options.scales.x, range);
        this.update();
        this.options.plugins.zoom.zoom.onZoom();
    };
    this.zoom = () => { this.zoomed = true; this.options.plugins.zoom.zoom.onZoom(); };
    this.resetZoom = () => { this.zoomed = false; };
    this.destroy = () => { this.destroyed = true; };
    this.resize = () => {};
    created.push(this);
}
const context = vm.createContext({
    Chart: FakeChart, Intl, Date, AbortController,
    Event: class { constructor(type) { this.type = type; } },
    document: {
        hidden: false, documentElement: {dataset: {bsTheme: "dark"}},
        getElementById: id => elements[id], querySelectorAll: selector => selector.startsWith("time") ? [] : [canvas],
        addEventListener: (name, callback) => { listeners[name] = callback; },
        dispatchEvent: event => { dispatched.push(event.type); listeners[event.type]?.(event); },
    },
    setTimeout: () => 1, clearTimeout() {}, setInterval() {},
    fetch: async () => ({ok: true, text: async () => "cards"}),
    DOMParser: class { parseFromString() { return {getElementById: () => ({innerHTML: "cards"})}; } },
});
vm.runInContext(source, context);
const charts = () => vm.runInContext('chartInstances["7"]', context);
const emit = (candle, updatedAt = Date.now(), interval = "1h") => {
    listeners.marketcandle({detail: {id: "7", source: "Binance", symbol: "BTC", interval, candle, updatedAt}});
    vm.runInContext('updateLiveChart("7")', context);
};

// Finansinio grafiko taisyklės išlieka: tik žvakės užuomina ir viena matoma X ašis.
assert.equal(charts().price.options.plugins.tooltip.intersect, true);
assert.equal(charts().price.options.plugins.legend.labels.filter({datasetIndex: 0}), false);
assert.equal(charts().price.options.scales.x.ticks.display, false);
assert.equal(charts().rsi.options.scales.x.ticks.display, true);
const labels = charts().price.options.plugins.tooltip.callbacks.label({raw: {o: 1, h: 2, l: 0.5, c: 1.12345}});
assert.equal(labels[3], "Close: " + new Intl.NumberFormat(undefined, {minimumFractionDigits: 3, maximumFractionDigits: 3}).format(1.12345));

// Naršyklėje skaičiuojami indikatoriai turi sutapti su Python testų matematiniais pavyzdžiais.
context.closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00];
assert.equal(vm.runInContext('calculateChartIndicators(closes.map(c => ({c}))).rsi.at(-1)', context), 66.25);
context.closes = Array(30).fill(10);
assert.equal(vm.runInContext('calculateChartIndicators(closes.map(c => ({c}))).rsi.at(-1)', context), 50);

const original = charts().price;
const stamp = Date.now();
emit({x: last, o: 60, h: 65, l: 59, c: 64}, stamp);
assert.equal(charts().price, original);
assert.equal(charts().price.data.datasets[0].data.at(-1).c, 64);
assert.equal(charts().price.data.datasets[1].data.at(-1).y, 50.7);
assert.equal(charts().price.data.datasets[2].data.at(-1).y, 35.58);
assert.equal(charts().rsi.data.datasets[0].data.at(-1).y, 100);
emit({x: last + hour, o: 64, h: 67, l: 63, c: 66}, stamp + 1);
assert.equal(charts().price.data.datasets[0].data.length, 61);
assert.equal(charts().price.scales.x.max, last + hour);
assert.equal(charts().rsi.scales.x.max, last + hour);

// Nauja žinutė negali panaikinti priartinimo, o senesnė negali perrašyti naujesnio OHLC.
vm.runInContext(`chartInstances["7"].price.zoomScale("x", {min: ${last - 4 * hour}, max: ${last + hour}})`, context);
emit({x: last + hour, o: 64, h: 68, l: 63, c: 67}, stamp + 2);
assert.equal(charts().price.scales.x.min, last - 4 * hour);
assert.equal(charts().rsi.scales.x.min, last - 4 * hour);
emit({x: last + hour, o: 64, h: 70, l: 63, c: 69}, stamp);
emit({x: last + hour, o: 64, h: 1, l: 63, c: 67}, stamp + 3);
assert.equal(charts().price.data.datasets[0].data.at(-1).c, 67);

// Neaktyvaus intervalo žvakė išsaugoma ir pritaikoma perjungus į 4h grafiką.
emit({x: last, o: 60, h: 85, l: 59, c: 80}, stamp + 4, "4h");
assert.equal(charts().price.data.datasets[0].data.at(-1).c, 67);
context.button = buttons["4h"];
vm.runInContext('changeTimeframe("7", "4h", button)', context);
assert.equal(charts().price.data.datasets[0].data.at(-1).c, 80);
await vm.runInContext("refreshDashboard()", context);
assert.equal(charts().price.data.datasets[0].data.at(-1).c, 80);
assert.equal(vm.runInContext('selectedTimeframes["7"]', context), "4h");
assert.ok(dispatched.includes("dashboardbeforerefresh"));
assert.ok(dispatched.includes("dashboardrefresh"));
assert.match(status.textContent, /Live candles/);
vm.runInContext('resetChartZoom("7")', context);
assert.equal(charts().price.scales.x.max, charts().times.at(-1));
assert.equal(charts().rsi.scales.x.max, charts().times.at(-1));
console.log("Chart checks passed: live OHLC, SMA/RSI, shared axis, tooltip precision, zoom, timeframe and HTML refresh.");
