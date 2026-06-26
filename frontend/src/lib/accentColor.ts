/**
 * Custom accent-color math (Wave 4). The picker hands a raw user-chosen hex; we
 * derive the four companion values the contract needs — an AA-guarded onAccent
 * ink (text drawn ON the fill), a deeper on-hue accent2 (border/dim), a weak
 * tint fill, and a focus ring — then layer them over whichever theme is active
 * as inline CSS-var overrides (see styles/accents.ts::applyCustomAccent).
 *
 * Self-contained on purpose: this is pure number-crunching with NO vanilla-
 * extract / contract import, so it loads under bare vitest (vitest.config.ts
 * intentionally omits the VE plugin). accent2 uses OKLCH so "deeper" means a
 * perceptually-even lightness drop that keeps the chosen hue + chroma intact.
 *
 * The only contrast we can guarantee for a freeform color is text-on-accent
 * (onAccent), so that is what we AA-guard; accent-on-surface is the user's
 * explicit choice and stays their responsibility.
 */

export interface DerivedAccent {
  /** Normalized #rrggbb fill. */
  accent: string;
  /** Deeper on-hue companion for borders / dim states. */
  accent2: string;
  /** Translucent accent tint for weak fills (mode-aware alpha). */
  accentWeak: string;
  /** AA-guarded ink for text/icons drawn on the fill (#000000 | #ffffff). */
  onAccent: string;
  /** Focus-ring box-shadow string at the theme's ring opacity. */
  focus: string;
}

/** WCAG 2.x normal-text threshold — the floor for legible text-on-accent. */
const AA_TEXT = 4.5;

/** The system jade signal; the safe fallback for an unparseable input. */
const JADE = '#2fd6a0';

const HEX_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

/** True for a `#rgb` / `#rrggbb` string (after trimming). */
export function isHexColor(value: string): boolean {
  return HEX_RE.test(value.trim());
}

/** Canonicalize to lowercase `#rrggbb` (expanding shorthand); null if invalid. */
export function normalizeHex(value: string): string | null {
  const s = value.trim().toLowerCase();
  if (!HEX_RE.test(s)) return null;
  if (s.length === 4) {
    return `#${s[1]}${s[1]}${s[2]}${s[2]}${s[3]}${s[3]}`;
  }
  return s;
}

function clamp01(x: number): number {
  return x < 0 ? 0 : x > 1 ? 1 : x;
}

/** Validated `#rrggbb` → its three 0..255 channels (bad input → black). */
function hexToRgb(hex: string): [number, number, number] {
  const full = normalizeHex(hex) ?? '#000000';
  const h = full.slice(1);
  return [0, 2, 4].map((i) => Number.parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
}

function toHex2(n: number): string {
  return n.toString(16).padStart(2, '0');
}

function rgbToHex(r: number, g: number, b: number): string {
  return `#${toHex2(r)}${toHex2(g)}${toHex2(b)}`;
}

/** sRGB 8-bit channel → linear-light 0..1 (WCAG / OKLab share this transfer). */
function linearize(c8: number): number {
  const c = c8 / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** Linear-light 0..1 → sRGB 8-bit channel. */
function delinearize(c: number): number {
  const v = c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
  return Math.round(clamp01(v) * 255);
}

/** sRGB relative luminance (WCAG 2.x) of a hex, 0..1. */
export function luminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b);
}

/** WCAG contrast ratio between two colors (1..21, order-independent). */
export function contrastRatio(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** `#rrggbb` → `rgba(r,g,b,a)` (alpha passed through as-authored). */
function rgba(hex: string, alpha: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${alpha})`;
}

// ---- OKLCH (Björn Ottosson) — used to deepen the accent on-hue ----

interface Oklch {
  L: number;
  C: number;
  h: number;
}

function hexToOklch(hex: string): Oklch {
  const [r8, g8, b8] = hexToRgb(hex);
  const r = linearize(r8);
  const g = linearize(g8);
  const b = linearize(b8);
  const l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b;
  const m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b;
  const s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b;
  const l_ = Math.cbrt(l);
  const m_ = Math.cbrt(m);
  const s_ = Math.cbrt(s);
  const L = 0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_;
  const a = 1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_;
  const bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_;
  return { L, C: Math.hypot(a, bb), h: Math.atan2(bb, a) };
}

function oklchToHex({ L, C, h }: Oklch): string {
  const a = C * Math.cos(h);
  const bb = C * Math.sin(h);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * bb;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * bb;
  const s_ = L - 0.0894841775 * a - 1.291485548 * bb;
  const l = l_ ** 3;
  const m = m_ ** 3;
  const s = s_ ** 3;
  const r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const b = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;
  return rgbToHex(delinearize(r), delinearize(g), delinearize(b));
}

/** Deepen a hex by scaling its OKLCH lightness (hue + chroma preserved). */
function deepen(hex: string, lightnessFactor: number): string {
  const c = hexToOklch(hex);
  return oklchToHex({ ...c, L: clamp01(c.L * lightnessFactor) });
}

/**
 * AA-guarded ink for content drawn ON an accent fill. Prefers white (filled
 * accent chips read as light-on-color); when white fails AA the guard flips to
 * black, which is then guaranteed >=4.5:1 (white only fails once the accent is
 * light enough that black clears ~4.67:1).
 */
export function onAccentInk(hex: string): string {
  return contrastRatio('#ffffff', hex) >= AA_TEXT ? '#ffffff' : '#000000';
}

/**
 * Derive the full accent companion set from a user-chosen hex. `isLight` picks
 * the theme-mode alphas (weak tint + focus ring) so the override sits right on
 * either surface ramp. An unparseable hex falls back to the jade default.
 */
export function deriveAccent(hex: string, opts: { isLight?: boolean } = {}): DerivedAccent {
  const isLight = opts.isLight ?? false;
  const accent = normalizeHex(hex) ?? JADE;
  const weakAlpha = isLight ? 0.12 : 0.13;
  const ringAlpha = isLight ? 0.3 : 0.34;
  return {
    accent,
    accent2: deepen(accent, 0.82),
    accentWeak: rgba(accent, weakAlpha),
    onAccent: onAccentInk(accent),
    focus: `0 0 0 3px ${rgba(accent, ringAlpha)}`,
  };
}
