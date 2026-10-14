/**
 * Theme persistence utility.
 *
 * Theme preference is stored in localStorage as 'documind_theme'.
 * On first visit, the system preference (prefers-color-scheme) is used
 * as the default, falling back to 'dark'.
 *
 * The chosen theme is applied as a data-theme attribute on <html> so
 * every CSS variable defined in index.css responds immediately.
 * No page refresh is needed.
 */

const STORAGE_KEY = 'documind_theme';

export function getInitialTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch { /* localStorage unavailable */ }

  // Respect system preference on first visit
  if (typeof window !== 'undefined' && window.matchMedia) {
    if (window.matchMedia('(prefers-color-scheme: light)').matches) return 'light';
  }

  return 'dark';
}

export function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  try { localStorage.setItem(STORAGE_KEY, theme); } catch { /* ignore */ }
}

export function toggleTheme(current) {
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  return next;
}
