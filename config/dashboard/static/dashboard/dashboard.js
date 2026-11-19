// Browser-only search, filters and favorites.
(() => {
    const search = document.getElementById("instrument-search");
    const type = document.getElementById("instrument-type");
    const favoritesOnly = document.getElementById("favorites-only");
    const openPanels = {};
    let favorites = readFavorites();

    function readFavorites() {
        try {
            const saved = JSON.parse(localStorage.getItem("marketlens-favorites") || "[]");
            return new Set(Array.isArray(saved) ? saved.filter(id => typeof id === "string") : []);
        } catch (error) {
            return new Set();
        }
    }

    function applyFilters() {
        const query = search.value.trim().toLocaleLowerCase();
        const cards = document.querySelectorAll(".instrument-card");
        let visible = 0;
        cards.forEach(card => {
            const id = card.dataset.instrumentId;
            const favorite = favorites.has(id);
            const matches = `${card.dataset.name} ${card.dataset.symbol}`.toLocaleLowerCase().includes(query)
                && (!type.value || card.dataset.type === type.value)
                && (!favoritesOnly.checked || favorite);
            card.closest("[data-instrument-item]").hidden = !matches;
            const button = card.querySelector("[data-favorite-id]");
            button.textContent = favorite ? "★" : "☆";
            button.setAttribute("aria-pressed", String(favorite));
            button.setAttribute("aria-label", `${favorite ? "Remove" : "Add"} ${card.dataset.name} ${favorite ? "from" : "to"} favorites`);
            button.classList.toggle("text-warning", favorite);
            if (matches) {
                visible += 1;
            }
        });
        document.getElementById("filter-status").textContent = `Showing ${visible} of ${cards.length} instruments`;
        document.getElementById("no-filter-results").hidden = visible > 0 || cards.length === 0;
        document.dispatchEvent(new Event("dashboardfilterchange"));
    }

    document.addEventListener("click", event => {
        const button = event.target.closest("[data-favorite-id]");
        if (!button) {
            return;
        }
        const id = button.dataset.favoriteId;
        if (favorites.has(id)) {
            favorites.delete(id);
        } else {
            favorites.add(id);
        }
        try {
            localStorage.setItem("marketlens-favorites", JSON.stringify([...favorites]));
        } catch (error) {
            // Keep favorites usable when storage is blocked.
        }
        applyFilters();
    });
    search.addEventListener("input", applyFilters);
    type.addEventListener("change", applyFilters);
    favoritesOnly.addEventListener("change", applyFilters);
    document.addEventListener("dashboardbeforerefresh", () => {
        document.querySelectorAll("details[data-panel]").forEach(panel => {
            openPanels[panel.dataset.panel] = panel.open;
        });
    });
    document.addEventListener("dashboardrefresh", () => {
        document.querySelectorAll("details[data-panel]").forEach(panel => {
            panel.open = Boolean(openPanels[panel.dataset.panel]);
        });
        applyFilters();
    });
    window.addEventListener("storage", event => {
        if (event.key === "marketlens-favorites" || event.key === null) {
            favorites = readFavorites();
            applyFilters();
        }
    });
    applyFilters();
})();
