// Paleidimas su Node.js: node tests/prices.test.mjs. Tikros tinklo užklausos nevykdomos.
// Imituojami šaltinių pranešimai, kad būtų patikrintos klaidos, atkūrimas ir HTML pakeitimas.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(new URL("../config/dashboard/static/dashboard/prices.js", import.meta.url), "utf8");
let now = Date.now();
const timers = new Map();
let timerId = 0;
const listeners = {};
const emitted = [];
const sockets = [];
let requests = 0;
let responseOK = true;
let quotes = [
    {id: 4, quote: {price: 20, price_time: now - 1000, checked_at: now, currency: "USD"}},
    {id: 5, quote: null},
];

// Mažas DOM pakaitalas suteikia tik tuos laukus, kuriuos naudoja kainų modulis.
function makeCard(id, source, symbol) {
    const elements = {};
    for (const selector of ["[data-live-price]", "[data-price-status]", "[data-price-time]"]) {
        const classes = new Set();
        elements[selector] = {
            textContent: "Saved price", offsetWidth: 100,
            classList: {add: name => classes.add(name), remove: (...names) => names.forEach(name => classes.delete(name))},
            classes,
        };
    }
    return {dataset: {instrumentId: String(id), source, symbol}, querySelector: selector => elements[selector]};
}
let cards = [makeCard(1, "Binance", "BTC"), makeCard(2, "Binance", "SOL"),
    makeCard(3, "Hyperliquid", "HYPE"), makeCard(4, "YahooFinance", "NVDA"), makeCard(5, "YahooFinance", "SPY")];
const element = (id, name) => cards.find(card => card.dataset.instrumentId === String(id)).querySelector(`[data-${name}]`);
const document = {
    hidden: false,
    querySelectorAll: () => cards,
    getElementById: () => ({dataset: {pricesUrl: "/prices/"}}),
    addEventListener: (name, callback) => { listeners[name] = callback; },
    dispatchEvent: event => { emitted.push(event); },
};
const navigator = {onLine: true};

// WebSocket pakaitalas leidžia tiksliai valdyti prisijungimą, pranešimus ir nutrūkimus.
class FakeSocket {
    static OPEN = 1;
    constructor(url) { this.url = url; this.readyState = 0; this.sent = []; sockets.push(this); }
    open() { this.readyState = 1; this.onopen?.(); }
    send(message) { this.sent.push(JSON.parse(message)); }
    message(data) { this.onmessage?.({data: JSON.stringify(data)}); }
    close() { this.readyState = 3; this.onclose?.(); }
}
const context = vm.createContext({
    document, navigator, WebSocket: FakeSocket, Intl, AbortController,
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    Date: class extends Date { static now() { return now; } },
    window: {addEventListener: (name, callback) => { listeners[name] = callback; }},
    setTimeout: (callback, delay) => { timers.set(++timerId, {callback, delay}); return timerId; },
    clearTimeout: id => timers.delete(id),
    setInterval: (callback, delay) => { timers.set(++timerId, {callback, delay, interval: true}); return timerId; },
    fetch: async () => { requests += 1; return {ok: responseOK, json: async () => ({quotes})}; },
});

// Leidžia užbaigti asinchronines fetch ir JSON promise užduotis be tikro laukimo.
async function flush() { for (let i = 0; i < 8; i += 1) { await Promise.resolve(); } }
const pollYahoo = () => [...timers.values()].find(timer => timer.interval && timer.delay === 45000).callback();
vm.runInContext(source, context);
await flush();
assert.equal(sockets.length, 2);
for (const symbol of ["btcusdt", "solusdt"]) {
    assert.ok(sockets[0].url.includes(`${symbol}@miniTicker`));
    for (const interval of ["1h", "4h", "1d"]) {
        assert.ok(sockets[0].url.includes(`${symbol}@kline_${interval}`));
    }
}
assert.match(element(4, "live-price").textContent, /20\.00/);
assert.match(element(4, "price-time").textContent, /Quote:.*Checked:/);
assert.match(element(5, "price-status").textContent, /unavailable/);

const [binance, hyperliquid] = sockets;
binance.open();
hyperliquid.open();
assert.deepEqual(hyperliquid.sent[0], {method: "subscribe", subscription: {type: "allMids"}});
assert.equal(hyperliquid.sent.length, 4);
assert.match(element(1, "price-status").textContent, /waiting/);
binance.message({data: {e: "24hrMiniTicker", E: now, s: "BTCUSDT", c: "100"}});
assert.equal(element(1, "live-price").textContent, "100.00 USDT");
assert.equal(element(1, "price-status").textContent, "Live · Binance");
binance.message({data: {e: "24hrMiniTicker", E: now + 1, s: "BTCUSDT", c: "101"}});
assert.ok(element(1, "live-price").classes.has("price-up"));
binance.message({data: {e: "24hrMiniTicker", E: now - 1000, s: "BTCUSDT", c: "999"}});
binance.message({data: {e: "24hrMiniTicker", E: now + 2, s: "BTCUSDT", c: "NaN"}});
binance.onmessage({data: "invalid JSON"});
assert.equal(element(1, "live-price").textContent, "101.00 USDT");
hyperliquid.message({channel: "allMids", data: {mids: {HYPE: "45.123"}}});
assert.match(element(3, "live-price").textContent, /45\.123/);
assert.equal(element(3, "price-status").textContent, "Live · Hyperliquid");
binance.message({data: {e: "kline", E: now, s: "BTCUSDT", k: {i: "1h", t: now - 1000, o: "100", h: "102", l: "99", c: "101"}}});
assert.equal(emitted.at(-1).type, "marketcandle");
assert.equal(emitted.at(-1).detail.candle.h, 102);
hyperliquid.message({channel: "candle", data: {s: "HYPE", i: "4h", t: now - 1000, o: "40", h: "46", l: "39", c: "45"}});
assert.equal(emitted.at(-1).detail.source, "Hyperliquid");
assert.equal(emitted.at(-1).detail.interval, "4h");
assert.equal(emitted.at(-1).detail.candle.c, 45);

// Minutinis kortelių pakeitimas turi atkurti srauto kainas ir nekurti papildomų ryšių.
cards = cards.map(card => makeCard(card.dataset.instrumentId, card.dataset.source, card.dataset.symbol));
listeners.dashboardrefresh();
assert.equal(element(1, "live-price").textContent, "101.00 USDT");
assert.match(element(4, "live-price").textContent, /20\.00/);
assert.equal(sockets.length, 2);

// Nutrūkus tinklui išlieka ankstesnės kainos; prisijungimas atkuriamas vienu bandymu.
binance.close();
assert.match(element(1, "price-status").textContent, /Disconnected/);
const retry = [...timers.entries()].find(([, timer]) => !timer.interval && timer.delay === 1000);
assert.ok(retry);
timers.delete(retry[0]);
retry[1].callback();
assert.equal(sockets.length, 3);
sockets[2].open();
responseOK = false;
await pollYahoo();
assert.match(element(4, "price-status").textContent, /unavailable/);
assert.match(element(4, "live-price").textContent, /20\.00/);
responseOK = true;
quotes = [{id: 4, quote: {price: 19, price_time: now + 1000, checked_at: now + 2000, currency: "USD"}}];
await pollYahoo();
assert.match(element(4, "live-price").textContent, /19\.00/);
assert.ok(element(4, "live-price").classes.has("price-down"));

// Paslėpta kortelė nevykdo kainų užklausų; grįžus ryšiai ir kainų patikra atnaujinami.
document.hidden = true;
listeners.visibilitychange();
const requestCount = requests;
await pollYahoo();
assert.equal(requests, requestCount);
assert.equal(sockets[2].readyState, 3);
document.hidden = false;
listeners.visibilitychange();
await flush();
assert.equal(sockets.length, 5);
assert.equal(requests, requestCount + 1);
assert.equal(element(1, "live-price").textContent, "101.00 USDT");
navigator.onLine = false;
listeners.offline();
assert.match(element(1, "price-status").textContent, /Offline/);

// Ilgesnio sutrikimo metu naujesnė DB kaina turi pakeisti pasenusį naršyklės įrašą.
cards = cards.map(card => makeCard(card.dataset.instrumentId, card.dataset.source, card.dataset.symbol));
cards[0].dataset.savedPriceTime = new Date(now + 60000).toISOString();
listeners.dashboardrefresh();
assert.equal(element(1, "live-price").textContent, "Saved price");
// Tam pačiam ID priskyrus kitą simbolį ankstesnio instrumento kaina neturi būti naudojama.
cards[2] = makeCard(3, "Hyperliquid", "OTHER");
listeners.dashboardrefresh();
assert.equal(element(3, "live-price").textContent, "Saved price");

console.log("Price checks passed: source messages, invalid data, shared connections, HTML refresh, retry, Yahoo failure and visibility.");
