import { ACCENT_IDS, applyAccent, clearAccent, DEFAULT_ACCENT } from './accents';
import { DEFAULT_THEME, isLightTheme, THEME_IDS, type ThemeId, themeClassName } from './themes';

const STORAGE_KEY = 'mp-theme';
const ACCENT_KEY = 'mp-accent';

export function getStoredTheme(): ThemeId {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v && (THEME_IDS as string[]).includes(v)) return v as ThemeId;
  } catch {
    /* localStorage unavailable — fall through to default */
  }
  return DEFAULT_THEME;
}

export function getStoredAccent(): string {
  try {
    const v = localStorage.getItem(ACCENT_KEY);
    if (v && ACCENT_IDS.includes(v)) return v;
  } catch {
    /* localStorage unavailable — fall through to default */
  }
  return DEFAULT_ACCENT;
}

/** Apply the accent overrides for `accentId` against the surface mode of `themeId`. */
function paintAccent(accentId: string, themeId: ThemeId): void {
  if (accentId === DEFAULT_ACCENT) {
    // Default = the theme's own jade; hand accent back to the theme class.
    clearAccent();
  } else {
    applyAccent(accentId, isLightTheme(themeId));
  }
}

/** Set the theme class on <html> and re-apply the active accent for its mode. */
export function applyTheme(id: ThemeId): void {
  const el = document.documentElement;
  for (const t of THEME_IDS) el.classList.remove(themeClassName(t));
  el.classList.add(themeClassName(id));
  // Accent is mode-aware (light vs dark hex), so re-paint it on every theme swap.
  paintAccent(getStoredAccent(), id);
}

/**
 * Persist the appearance prefs (theme + accent), best-effort. The backend PUT
 * REPLACES the whole blob, so we must read the current prefs first and merge
 * theme/accent into them — otherwise a theme/accent change would wipe the user's
 * saved nav order, dashboard layout, and module prefs. Mirrors NavCustomizer's
 * withSurfacePrefs (client-side merge → full-blob PUT).
 */
function persist(theme: ThemeId, accent: string): void {
  void (async () => {
    let current: { version?: number; ui?: Record<string, unknown> } = {};
    try {
      const res = await fetch('/api/ui-prefs');
      if (res.ok) current = await res.json();
    } catch {
      /* offline / no backend — fall back to a minimal blob below */
    }
    const ui = { ...(current.ui ?? {}), theme, accent };
    fetch('/api/ui-prefs', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version: current.version ?? 1, ui }),
    }).catch(() => {});
  })();
}

/** Persist (localStorage + best-effort backend) and apply the theme. */
export function setTheme(id: ThemeId): void {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore persistence failure */
  }
  applyTheme(id);
  persist(id, getStoredAccent());
}

/** Persist + apply the accent (against the current theme's surface mode). */
export function setAccent(id: string): void {
  try {
    localStorage.setItem(ACCENT_KEY, id);
  } catch {
    /* ignore persistence failure */
  }
  paintAccent(id, getStoredTheme());
  persist(getStoredTheme(), id);
}
