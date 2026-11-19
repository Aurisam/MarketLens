function getPreferredTheme() {
    try {
        const savedTheme = localStorage.getItem("marketlens-theme");
        if (savedTheme === "dark" || savedTheme === "light") {
            return savedTheme;
        }
    } catch (error) {
        // Fall back to the system theme when storage is blocked.
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
        // Keep the theme usable when storage is blocked.
    }
    updateThemeButton();
    document.dispatchEvent(new Event("themechange"));
}

// Apply the theme before rendering to avoid a flash of the wrong colors.
document.documentElement.dataset.bsTheme = getPreferredTheme();
document.addEventListener("DOMContentLoaded", updateThemeButton);
