import { describe, expect, it } from 'vitest';
import { lightValues } from './light.values';

/**
 * WCAG AA contract for the LIGHT theme. Locks the surface/text/accent/rating
 * VALUES (light.values.ts) at the contrast ratios the design system promises, so
 * a future value tweak that breaks legibility fails CI instead of shipping.
 *
 * Thresholds (WCAG 2.x): normal text >=4.5:1, large/UI non-text >=3:1. The math
 * is inlined (bare vitest doesn't load the vanilla-extract plugin, so we cannot
 * import the contrast helper out of accents.ts, which pulls in the .css.ts
 * contract — see vitest.config.ts).
 */

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

const c = lightValues.color;

/** Every surface step a piece of chrome can sit on. */
const ALL_SURFACES = ['void', 'sunken', 'panel', 'panel2', 'surface', 'hover', 'active'] as const;
/** Primary reading surfaces — where body + label text actually renders. */
const PRIMARY_SURFACES = ['void', 'panel', 'surface', 'panel2'] as const;
/** Surfaces the quietest micro-counts (fore4) sit on (never hover/active fills). */
const MICRO_SURFACES = ['void', 'sunken', 'panel', 'panel2', 'surface'] as const;

const AA_NORMAL = 4.5;
const AA_UI = 3;

function minContrast(fg: string, surfaces: readonly (keyof typeof c)[]): number {
  return Math.min(...surfaces.map((s) => contrast(fg, c[s] as string)));
}

describe('light theme — WCAG AA', () => {
  it.each([
    'fore',
    'fore2',
    'fore3',
  ] as const)('%s is AA-normal (>=4.5) on every surface', (token) => {
    expect(minContrast(c[token], ALL_SURFACES)).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  it('fore4 micro-counts are AA-normal on the surfaces they sit on', () => {
    expect(minContrast(c.fore4, MICRO_SURFACES)).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  it('accent clears UI non-text contrast (>=3) on every surface', () => {
    expect(minContrast(c.accent, ALL_SURFACES)).toBeGreaterThanOrEqual(AA_UI);
  });

  it('accent2 (border/dim) clears UI non-text contrast (>=3) on every surface', () => {
    expect(minContrast(c.accent2, ALL_SURFACES)).toBeGreaterThanOrEqual(AA_UI);
  });

  it('onAccent ink is AA-normal (>=4.5) on the accent fill (button labels)', () => {
    expect(contrast(c.onAccent, c.accent)).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  it.each([
    'sfw',
    'sugg',
    'nsfw',
    'unrated',
    'star',
  ] as const)('rating color %s is AA-normal (>=4.5) as label text on primary surfaces', (token) => {
    expect(minContrast(c[token], PRIMARY_SURFACES)).toBeGreaterThanOrEqual(AA_NORMAL);
  });
});
