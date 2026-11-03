function getPreferredTheme() {
    try {
        const savedTheme = localStorage.getItem("marketlens-theme");
        if (savedTheme === "dark" || savedTheme === "light") {
            return savedTheme;
        }
    } catch (error) {
        // Use the browser preference when storage is unavailable.
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function updateThemeButton() {
    const button = document.getElementById("theme-toggle");
    if (button) {
        const isDark = document.documentElement.dataset.bsTheme === "dark";
        button.textContent = isDark ? "Light mode" : "Dark mode";
        button.setAttribute("aria-pressed", String(isDark));
    }
}

function toggleTheme() {
    const theme = document.documentElement.dataset.bsTheme === "dark" ? "light" : "dark";
    document.documentElement.dataset.bsTheme = theme;
    try {
        localStorage.setItem("marketlens-theme", theme);
    } catch (error) {
        // Theme switching still works for this page without storage.
    }
    updateThemeButton();
    document.dispatchEvent(new Event("themechange"));
}

document.documentElement.dataset.bsTheme = getPreferredTheme();
document.addEventListener("DOMContentLoaded", updateThemeButton);
