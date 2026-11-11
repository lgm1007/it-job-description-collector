// The stored theme is applied by an inline script in app/layout.tsx, before the first paint.
const THEME_KEY = "jdc-theme";
const BACKGROUND = { dark: "#0c0f0e", light: "#f8f7f2" };

export const THEME_SCRIPT = `try {
  const t = localStorage.getItem("${THEME_KEY}");
  if (t) {
    document.documentElement.dataset.theme = t;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", ${JSON.stringify(BACKGROUND)}[t]);
  }
} catch (e) {}`;

export function toggleTheme(): void {
  const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", BACKGROUND[next]);
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch {
    // private mode: the theme just won't be remembered
  }
}
