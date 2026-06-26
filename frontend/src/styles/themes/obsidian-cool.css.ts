import { createTheme } from '@vanilla-extract/css';
import { vars } from '../contract.css';

/**
 * OBSIDIAN-COOL — a dark preset with a cool near-black ramp + bright cyan accent.
 *
 * Built from the Pigment value object (theme.css.ts) with surface/accent/text/
 * scrim deltas only. Rating colors are kept IDENTICAL to Pigment (data, not
 * theme). WCAG AA: cool near-white `fore` on the near-black panels, bright cyan
 * `accent` well above 3:1 on panel for UI / focus.
 */
export const obsidianCoolClass = createTheme(vars, {
  color: {
    // Surfaces — cool near-black ramp (obsidian floor -> raised chrome)
    void: '#070809',
    sunken: '#0c0e12',
    panel: '#0f1218',
    panel2: '#151a22',
    surface: '#1b212b',
    hover: '#252d39',
    active: '#303a48',

    // Hairlines & borders
    hair: '#1e242d',
    line: '#2d3641',
    line2: '#3f4a59',

    // Text — cool near-white ramp
    fore: '#f1f5fa',
    fore2: '#c6cdd8',
    fore3: '#8fa0b0',
    fore4: '#85929f',
    onAccent: '#03131b',

    // Bright cyan accent (restrained: focus, single active marker, ⌘K)
    accent: '#36c9ff',
    accent2: '#1f7fa6',
    accentWeak: 'rgba(54,201,255,0.13)',

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
    focus: '0 0 0 3px rgba(54,201,255,.35)',
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
    strong: 'rgba(6,7,10,.92)',
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
