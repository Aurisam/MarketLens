// Paleidimas: node tests/dashboard.test.mjs. Tikrinama paieška, filtrai ir localStorage be naršyklės.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(new URL("../config/dashboard/static/dashboard/dashboard.js", import.meta.url), "utf8");
const storage = new Map();
const listeners = {};
let storageBlocked = false;

// Kortelė ir jos žvaigždutė pateikia tik tuos DOM metodus, kuriuos naudoja dashboard.js.
function makeCard(id, name, symbol, type) {
    const item = {hidden: false};
    const attributes = {};
    const button = {dataset: {favoriteId: String(id)}, textContent: "☆",
        setAttribute: (key, value) => { attributes[key] = value; }, classList: {toggle() {}}, attributes};
    button.closest = () => button;
    return {dataset: {instrumentId: String(id), name, symbol, type}, item, button,
        closest: () => item, querySelector: () => button};
}
let cards = [makeCard(1, "Bitcoin", "BTC", "Crypto"), makeCard(2, "NVIDIA", "NVDA", "Stock"), makeCard(3, "S&P500", "SPY", "ETF")];
let panels = [{dataset: {panel: "signal-1"}, open: true}];
const elements = {};
for (const id of ["instrument-search", "instrument-type", "favorites-only", "filter-status", "no-filter-results"]) {
    elements[id] = {value: "", checked: false, hidden: true, events: {}, addEventListener(name, callback) { this.events[name] = callback; }};
}
const context = vm.createContext({
    document: {
        getElementById: id => elements[id],
        querySelectorAll: selector => selector.startsWith("details") ? panels : cards,
        addEventListener: (name, callback) => { listeners[name] = callback; }, dispatchEvent() {},
    },
    window: {addEventListener: (name, callback) => { listeners[name] = callback; }},
    Event: class { constructor(type) { this.type = type; } },
    localStorage: {
        getItem: key => { if (storageBlocked) throw new Error("Blocked"); return storage.get(key) ?? null; },
        setItem: (key, value) => { if (storageBlocked) throw new Error("Blocked"); storage.set(key, value); },
    },
});
vm.runInContext(source, context);
assert.equal(elements["filter-status"].textContent, "Showing 3 of 3 instruments");
elements["instrument-search"].value = "bTc";
elements["instrument-search"].events.input();
assert.deepEqual(cards.map(card => card.item.hidden), [false, true, true]);
elements["instrument-type"].value = "Stock";
elements["instrument-type"].events.change();
assert.equal(elements["no-filter-results"].hidden, false);
elements["instrument-search"].value = "";
elements["instrument-search"].events.input();
assert.deepEqual(cards.map(card => card.item.hidden), [true, false, true]);
elements["instrument-type"].value = "";
listeners.click({target: cards[0].button});
assert.equal(cards[0].button.attributes["aria-pressed"], "true");
assert.equal(storage.get("marketlens-favorites"), '["1"]');
elements["favorites-only"].checked = true;
elements["favorites-only"].events.change();
assert.deepEqual(cards.map(card => card.item.hidden), [false, true, true]);

// Naujas kortelių HTML nepanaikina filtro, mėgstamų instrumentų ir išskleisto paaiškinimo.
listeners.dashboardbeforerefresh();
cards = cards.map(card => makeCard(card.dataset.instrumentId, card.dataset.name, card.dataset.symbol, card.dataset.type));
panels = [{dataset: {panel: "signal-1"}, open: false}];
listeners.dashboardrefresh();
assert.equal(panels[0].open, true);
assert.deepEqual(cards.map(card => card.item.hidden), [false, true, true]);
assert.equal(cards[0].button.textContent, "★");
storage.set("marketlens-favorites", '["2"]');
listeners.storage({key: "marketlens-favorites"});
assert.deepEqual(cards.map(card => card.item.hidden), [true, false, true]);
storageBlocked = true;
listeners.click({target: cards[1].button});
assert.equal(elements["filter-status"].textContent, "Showing 0 of 3 instruments");
assert.equal(cards[1].button.attributes["aria-pressed"], "false");

console.log("Dashboard checks passed: combined filters, favorites, HTML refresh, open panels and blocked storage.");
