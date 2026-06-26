import { createTheme } from '@vanilla-extract/css';
import { vars } from '../contract.css';

/**
 * SLATE-WARM — a dark preset with a warm Pigment-derived ramp + amber accent.
 *
 * Built from the Pigment value object (theme.css.ts) with surface/accent/text/
 * scrim deltas only. Rating colors (sfw/sugg/nsfw/unrated/*Weak/star) are kept
 * IDENTICAL to Pigment — rating semantics stay consistent across themes; data-
 * driven label colors are a Wave 2b concern. WCAG AA: warm near-white `fore` on
 * the warm panels, amber `accent` >3:1 on panel for UI.
 */
export const slateWarmClass = createTheme(vars, {
  color: {
    // Surfaces — warm Pigment-derived ramp (deep umber floor -> raised chrome)
    void: '#0d0c0a',
    sunken: '#141210',
    panel: '#1a1714',
    panel2: '#211d18',
    surface: '#2a251f',
    hover: '#352f27',
    active: '#403930',

    // Hairlines & borders
    hair: '#1e242d',
    line: '#2d3641',
    line2: '#3f4a59',

    // Text — warm near-white ramp
    fore: '#f6f3ee',
    fore2: '#c6cdd8',
    fore3: '#a39a8c',
    fore4: '#938a7c',
    onAccent: '#1a1408',

    // Amber accent (restrained: focus, single active marker, ⌘K)
    accent: '#d4a955',
    accent2: '#9a7a3a',
    accentWeak: 'rgba(212,169,85,0.13)',

    // Rating colors — UNCHANGED from Pigment (data, never chrome)
    sfw: '#4fcf8f',
    sugg: '#f0bd55',
    nsfw: '#ef6f6f',
    unrated: '#7c8a9a',
    star: '#f0bd55',
    sfwWeak: 'rgba(79,207,143,.15)',
    suggWeak: 'rgba(240,189,85,.15)',
    nsfwWeak: 'rgba(239,111,111,.15)',
    negBg: '#2b1c1f',
    negLine: '#5d3338',

    // Disabled / inert
    disabledBg: '#171b21',
    disabledFore: '#566070',
  },

  shadow: {
    pop: '0 24px 60px rgba(0,0,0,.65)',
    focus: '0 0 0 3px rgba(212,169,85,.35)',
  },

  radius: {
    small: '6px',
    button: '8px',
    panel: '16px',
    tile: '12px',
    pill: '999px',
  },

  space: {
    '0.5': '2px',
    '1': '4px',
    '1.5': '6px',
    '2': '8px',
    '3': '12px',
    '4': '16px',
    '5': '24px',
    '6': '32px',
    '7': '48px',
    '8': '64px',
    '9': '96px',
  },

  size: {
    controlXs: '24px',
    controlSm: '28px',
    controlMd: '32px',
    controlLg: '38px',
    rowH: '38px',
    rowHDense: '30px',
    barH: '60px',
  },

  scrim: {
    strong: 'rgba(13,12,10,.92)',
    soft: 'rgba(6,7,10,.45)',
  },

  font: {
    sans: '"Schibsted Grotesk Variable", -apple-system, "Segoe UI", Roboto, system-ui, sans-serif',
    mono: '"Schibsted Grotesk Variable", -apple-system, "Segoe UI", Roboto, system-ui, sans-serif',
  },

  fontSize: {
    micro: '11px',
    label: '12px',
    meta: '13px',
    heading: '14px',
    body: '15px',
    brand: '18px',
    display: '20px',
  },

  fontWeight: {
    reg: '400',
    med: '500',
    semi: '600',
    bold: '700',
  },

  letterSpacing: {
    label: '0.06em',
    tight: '-0.01em',
  },

  lineHeight: {
    tight: '1.2',
    snug: '1.35',
    base: '1.5',
  },

  motion: {
    durFast: '120ms',
    durBase: '180ms',
    easeOut: 'cubic-bezier(0.25, 1, 0.5, 1)',
  },
});
