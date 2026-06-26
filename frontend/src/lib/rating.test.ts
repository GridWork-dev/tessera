import { describe, expect, it, vi } from 'vitest';

// `rating.ts` imports the vanilla-extract theme contract, which can only be
// evaluated inside a `.css.ts` build context (the VE plugin), not under bare
// vitest. We mock it with `var(--...)` placeholders that mirror what
// `createThemeContract` produces at runtime, so we can pin the MECHANISM of the
// rating color path in pure-logic test land.
vi.mock('../styles/contract.css', () => ({
  vars: {
    color: {
      sfw: 'var(--sfw)',
      sugg: 'var(--sugg)',
      nsfw: 'var(--nsfw)',
      unrated: 'var(--unrated)',
      sfwWeak: 'var(--sfwWeak)',
      suggWeak: 'var(--suggWeak)',
      nsfwWeak: 'var(--nsfwWeak)',
    },
  },
}));

const { RATINGS, ratingColor, ratingLabel, ratingWeak } = await import('./rating');

// These tests PIN the actual rating-color mechanism so the spec and the code
// cannot silently drift again (Wave 2c reconciliation). Rating color is a
// SEMANTIC THEME TOKEN (vars.color.*, DESIGN.md "rating colors, semantic data,
// never chrome") — it is NOT a per-label `label_definitions.color` hex data
// value, and it is NOT delivered via `assignInlineVars`. Labels (the data-color
// path) live in labelColor.ts and are a separate mechanism.

describe('rating color mechanism (Wave 2c reconciliation)', () => {
  it('maps each rating to its theme contract token, distinct per rating', () => {
    expect(ratingColor('sfw')).toBe('var(--sfw)');
    expect(ratingColor('suggestive')).toBe('var(--sugg)');
    expect(ratingColor('nsfw')).toBe('var(--nsfw)');
    expect(ratingColor(null)).toBe('var(--unrated)');
    const distinct = new Set(RATINGS.map((r) => ratingColor(r)));
    expect(distinct.size).toBe(RATINGS.length);
  });

  it('returns a theme-token var() reference, never a raw hex data color', () => {
    // A label_definitions.color value would be a literal hex (e.g. #d27a7a).
    // Rating colors resolve to a vanilla-extract contract var() instead — proof
    // the rating path is NOT the data-driven label color path.
    for (const r of RATINGS) {
      const c = ratingColor(r);
      expect(c).toMatch(/^var\(/);
      expect(c).not.toMatch(/^#/);
    }
  });

  it('weak tints are theme tokens too (or transparent for unrated)', () => {
    expect(ratingWeak('sfw')).toBe('var(--sfwWeak)');
    expect(ratingWeak('suggestive')).toBe('var(--suggWeak)');
    expect(ratingWeak('nsfw')).toBe('var(--nsfwWeak)');
    expect(ratingWeak(null)).toBe('transparent');
  });

  it('always pairs color with a text label (never color-only meaning)', () => {
    expect(ratingLabel('sfw')).toBe('SFW');
    expect(ratingLabel('suggestive')).toBe('SUGG');
    expect(ratingLabel('nsfw')).toBe('NSFW');
    expect(ratingLabel(null)).toBe('UNRATED');
  });
});
