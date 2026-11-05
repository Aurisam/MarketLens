// Pirmiausia naudoja išsaugotą pasirinkimą, o jo nesant – naršyklės sistemos temą.
function getPreferredTheme() {
    try {
        const savedTheme = localStorage.getItem("marketlens-theme");
        if (savedTheme === "dark" || savedTheme === "light") {
            return savedTheme;
        }
    } catch (error) {
        // Jei localStorage neprieinamas, toliau naudojamas sistemos temos pasirinkimas.
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

// Atnaujina temos mygtuko tekstą ir pagalbinėms technologijoms skirtą aria-pressed būseną.
function updateThemeButton() {
    const button = document.getElementById("theme-toggle");
    if (button) {
        const isDark = document.documentElement.dataset.bsTheme === "dark";
        button.textContent = isDark ? "Light mode" : "Dark mode";
        button.setAttribute("aria-pressed", String(isDark));
    }
}

// Perjungia temą, išsaugo pasirinkimą ir praneša grafikams, kad reikia pakeisti spalvas.
function toggleTheme() {
    const theme = document.documentElement.dataset.bsTheme === "dark" ? "light" : "dark";
    document.documentElement.dataset.bsTheme = theme;
    try {
        localStorage.setItem("marketlens-theme", theme);
    } catch (error) {
        // Tema šiame puslapyje veikia ir tada, kai pasirinkimo naršyklė neleidžia išsaugoti.
    }
    updateThemeButton();
    document.dispatchEvent(new Event("themechange"));
}

// Šis failas kraunamas head dalyje: tema nustatoma prieš parodant puslapį.
document.documentElement.dataset.bsTheme = getPreferredTheme();
document.addEventListener("DOMContentLoaded", updateThemeButton);
