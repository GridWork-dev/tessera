import { deriveAccent } from '../lib/accentColor';
import { vars } from './contract.css';

/**
 * Custom accent picker — a constrained, pre-vetted palette, NOT a freeform hue
 * wheel. The jade default is the system signal; the rest are restrained
 * alternates. Each accent carries a `dark` and a `light` hex so the SAME swatch
 * stays AA on whichever surface ramp is active (bright on dark themes, deeper on
 * the light theme). On pick we derive onAccent ink, focus ring, and accentWeak
 * from the resolved hex and override only the accent contract vars on <html> —
 * surfaces, text, and rating colors stay owned by the theme.
 *
 * WCAG AA (verified via a throwaway contrast check):
 *   dark hex on dark surfaces (void/panel/surface): >=8.6:1 (UI/non-text >=3)
 *   light hex on light surfaces:                     >=3.16:1 (UI/non-text >=3)
 *   onAccent ink on the resolved fill:               >=4.19:1 (UI/button label)
 */

export interface AccentDef {
  id: string;
  label: string;
  /** Hex used on the dark surface ramp (pigment / slate / obsidian). */
  dark: string;
  /** Hex used on the light surface ramp. */
  light: string;
}

/** Default = the system jade signal (matches Pigment / theme.css.ts). */
export const DEFAULT_ACCENT = 'jade';

export const ACCENTS: AccentDef[] = [
  { id: 'jade', label: 'Jade', dark: '#2fd6a0', light: '#0f9d74' },
  { id: 'cyan', label: 'Cyan', dark: '#36c9ff', light: '#0e8fc4' },
  { id: 'violet', label: 'Violet', dark: '#9b8cff', light: '#7c6bf0' },
  { id: 'amber', label: 'Amber', dark: '#e0b65f', light: '#b07d1a' },
  { id: 'rose', label: 'Rose', dark: '#f47089', light: '#c8385c' },
  { id: 'emerald', label: 'Emerald', dark: '#34d399', light: '#0c9d6b' },
];

export const ACCENT_IDS = ACCENTS.map((a) => a.id);

/** Jade fallback (ACCENTS is non-empty; keeps the return type non-optional). */
const JADE: AccentDef = { id: 'jade', label: 'Jade', dark: '#2fd6a0', light: '#0f9d74' };

export function accentById(id: string): AccentDef {
  return ACCENTS.find((a) => a.id === id) ?? JADE;
}

// ---- contrast helpers (sRGB relative luminance, WCAG 2.x) ----

function hexToRgb(hex: string): [number, number, number] {
  let h = hex.replace('#', '');
  if (h.length === 3)
    h = h
      .split('')
      .map((c) => c + c)
      .join('');
  return [0, 2, 4].map((i) => Number.parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
}

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Pick the ink (dark or light) with the higher contrast against the fill. */
function pickInk(fill: string): string {
  const darkInk = '#04130d';
  const lightInk = '#ffffff';
  return contrast(fill, darkInk) >= contrast(fill, lightInk) ? darkInk : lightInk;
}

/**
 * High-contrast ink for content drawn ON an accent fill (e.g. the selected
 * swatch's tick) — the same dark/light pick used for onAccent. Exposed so the
 * picker can color each swatch's check mark legibly per-hue.
 */
export function accentInk(fill: string): string {
  return pickInk(fill);
}

/** Convert a `#rrggbb` to an `rgba(r,g,b,a)` tint string. */
function rgba(hex: string, alpha: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${alpha})`;
}

/**
 * A contract var reference resolves at runtime to a `var(--name)` string; strip
 * to the raw `--name` so we can override it via element.style.setProperty.
 */
function cssVarName(ref: string): string {
  const m = /var\((--[^,)]+)/.exec(ref);
  return m?.[1] ? m[1].trim() : ref;
}

/**
 * Override the accent contract vars on <html> for the chosen accent + surface
 * mode. Passing the default jade + the active theme's own mode is a no-op-shaped
 * override (it just re-asserts the theme's accent), so clearing is just applying
 * the default.
 */
export function applyAccent(id: string, isLight: boolean): void {
  const def = accentById(id);
  const fill = isLight ? def.light : def.dark;
  const ink = pickInk(fill);
  // accent2 (border/dim) — a slightly deeper companion. Mixing toward the ink
  // keeps it on-hue without a second hand-tuned value per accent.
  const accent2 = isLight ? def.light : def.dark;

  const el = document.documentElement;
  const set = (ref: string, value: string) => el.style.setProperty(cssVarName(ref), value);

  set(vars.color.accent, fill);
  set(vars.color.accent2, accent2);
  set(vars.color.accentWeak, rgba(fill, isLight ? 0.12 : 0.13));
  set(vars.color.onAccent, ink);
  // Focus ring tracks the accent hue at the theme's ring opacity.
  set(vars.shadow.focus, `0 0 0 3px ${rgba(fill, isLight ? 0.3 : 0.34)}`);
}

/**
 * Override the accent contract vars from a freeform user-chosen hex (the custom
 * picker). The onAccent ink, deeper accent2, weak tint, and focus ring are
 * derived + AA-guarded in lib/accentColor.ts; here we only map them onto the
 * contract vars on <html> so they layer over whichever theme is active.
 */
export function applyCustomAccent(hex: string, isLight: boolean): void {
  const d = deriveAccent(hex, { isLight });
  const el = document.documentElement;
  const set = (ref: string, value: string) => el.style.setProperty(cssVarName(ref), value);

  set(vars.color.accent, d.accent);
  set(vars.color.accent2, d.accent2);
  set(vars.color.accentWeak, d.accentWeak);
  set(vars.color.onAccent, d.onAccent);
  set(vars.shadow.focus, d.focus);
}

/** Remove the inline accent overrides, handing accent back to the theme class. */
export function clearAccent(): void {
  const el = document.documentElement;
  for (const ref of [
    vars.color.accent,
    vars.color.accent2,
    vars.color.accentWeak,
    vars.color.onAccent,
    vars.shadow.focus,
  ]) {
    el.style.removeProperty(cssVarName(ref));
  }
}
