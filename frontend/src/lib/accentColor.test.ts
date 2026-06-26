import { describe, expect, it } from 'vitest';
import {
  contrastRatio,
  deriveAccent,
  isHexColor,
  luminance,
  normalizeHex,
  onAccentInk,
} from './accentColor';

/**
 * Color-derivation math for the custom accent picker. The picker hands a raw
 * user-chosen hex to deriveAccent, which must return an AA-guarded onAccent ink
 * (text-on-accent), a deeper on-hue accent2 (border/dim), a weak tint, and a
 * focus ring — layered over whichever theme is active. These tests lock the
 * contrast guard and the variant derivation so a future math tweak that breaks
 * legibility fails CI instead of shipping.
 */

const AA_TEXT = 4.5;

describe('accentColor — hex parsing', () => {
  it('accepts #rrggbb and #rgb, rejects garbage', () => {
    expect(isHexColor('#2fd6a0')).toBe(true);
    expect(isHexColor('#abc')).toBe(true);
    expect(isHexColor('2fd6a0')).toBe(false);
    expect(isHexColor('not-a-color')).toBe(false);
    expect(isHexColor('#xyzxyz')).toBe(false);
  });

  it('normalizes to lowercase #rrggbb (expanding shorthand)', () => {
    expect(normalizeHex('#2FD6A0')).toBe('#2fd6a0');
    expect(normalizeHex('#ABC')).toBe('#aabbcc');
    expect(normalizeHex('  #Fff ')).toBe('#ffffff');
    expect(normalizeHex('garbage')).toBeNull();
  });
});

describe('accentColor — contrast primitives', () => {
  it('black on white is the maximal 21:1', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 1);
  });

  it('luminance is monotonic (white > mid > black)', () => {
    expect(luminance('#ffffff')).toBeGreaterThan(luminance('#808080'));
    expect(luminance('#808080')).toBeGreaterThan(luminance('#000000'));
  });
});

describe('accentColor — onAccent contrast guard', () => {
  it('picks white ink on a dark accent', () => {
    expect(onAccentInk('#1b2a4a')).toBe('#ffffff');
  });

  it('falls back to black ink when white fails AA on a light accent', () => {
    // White text on a near-white accent fails AA; the guard flips to black.
    expect(contrastRatio('#ffffff', '#ffd400')).toBeLessThan(AA_TEXT);
    expect(onAccentInk('#ffd400')).toBe('#000000');
  });

  it('always clears AA (>=4.5) for text-on-accent across a hue battery', () => {
    for (const hex of [
      '#2fd6a0', // jade default
      '#ffd400', // bright yellow
      '#1b2a4a', // deep navy
      '#808080', // mid grey (worst case for black/white pick)
      '#e0506e', // rose
      '#36c9ff', // cyan
      '#9b8cff', // violet
    ]) {
      expect(contrastRatio(onAccentInk(hex), hex)).toBeGreaterThanOrEqual(AA_TEXT);
    }
  });
});

describe('accentColor — deriveAccent variant derivation', () => {
  it('normalizes the fill and AA-guards onAccent', () => {
    const d = deriveAccent('#2FD6A0');
    expect(d.accent).toBe('#2fd6a0');
    expect(contrastRatio(d.onAccent, d.accent)).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it('derives a deeper (lower-luminance) on-hue accent2 for borders/dim', () => {
    const d = deriveAccent('#2fd6a0');
    expect(d.accent2).not.toBe(d.accent);
    expect(luminance(d.accent2)).toBeLessThan(luminance(d.accent));
    expect(isHexColor(d.accent2)).toBe(true);
  });

  it('weak tint + focus ring carry the accent rgb and the mode alpha', () => {
    const dark = deriveAccent('#2fd6a0', { isLight: false });
    expect(dark.accentWeak).toBe('rgba(47,214,160,0.13)');
    expect(dark.focus).toBe('0 0 0 3px rgba(47,214,160,0.34)');

    const light = deriveAccent('#2fd6a0', { isLight: true });
    expect(light.accentWeak).toBe('rgba(47,214,160,0.12)');
    expect(light.focus).toBe('0 0 0 3px rgba(47,214,160,0.3)');
  });

  it('tolerates a bad hex by falling back to the jade default', () => {
    const d = deriveAccent('nonsense');
    expect(d.accent).toBe('#2fd6a0');
  });
});
