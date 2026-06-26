import { createTheme, globalStyle } from '@vanilla-extract/css';
import { vars } from './contract.css';

/**
 * ============================================================================
 * PIGMENT — the committed design system. See DESIGN.md.
 * ============================================================================
 *
 * Committed-signal dark: a near-black surface ramp (#0a0b0d floor) carries ONE
 * ownable jade signal (#2fd6a0) as the brand — the "lit tessera" you are hunting
 * for in the grid. The accent is restrained in coverage (<=10%) but committed in
 * identity: focus rings, the single active marker, ⌘K, primary actions. Chrome
 * recedes; imagery + data dominate. Rating colors are semantic data, never chrome.
 * Typeface = Schibsted Grotesk (one family, UI + wordmark + tabular numerics),
 * self-hosted via @fontsource-variable (no external CDN — local-first / privacy).
 *
 * Dark-only by design (a curation tool used for long focused sessions in dim
 * rooms; light surfaces would fight the imagery). WCAG AA verified: fore on void
 * 17.3:1, fore2 7.8:1+, fore3 4.99:1 on the lightest surface (AA normal), accent
 * 8.9:1+ on every surface, onAccent on jade 10.2:1. fore4 clears AA-normal
 * (>=4.5:1) on void/sunken/panel/panel2 — the surfaces its micro-counts sit on.
 *
 * Re-theming contract: change VALUES here only — the token SHAPE lives in
 * contract.css.ts. Alternate dark themes (slate-warm / obsidian-cool) are
 * separate createTheme files selectable via the Appearance switcher.
 */
export const themeClass = createTheme(vars, {
  color: {
    // Surfaces — near-black ramp (deep floor -> raised chrome)
    void: '#0a0b0d',
    sunken: '#0e1013',
    panel: '#121419',
    panel2: '#171a20',
    surface: '#1b1e25',
    hover: '#242833',
    active: '#2f3540',

    // Hairlines & borders
    hair: '#20242b',
    line: '#262a32',
    line2: '#373d48',

    // Text
    fore: '#eef0f4',
    fore2: '#abb1bd',
    // fore3 (tertiary/labels) at #868d98 clears AA-normal (>=4.5:1) on every
    // surface incl. the lightest (#1b1e25 -> 4.99:1).
    fore3: '#868d98',
    // fore4 (quietest) — clears AA-normal (>=4.5:1) on the surfaces micro text
    // sits on (void 5.52 / sunken 5.35 / panel 5.17 / panel2 4.89). Quieter than
    // fore3 but still readable; micro-counts only, never body.
    fore4: '#828893',
    onAccent: '#04130d',

    // Jade signal accent (committed identity: focus, active marker, ⌘K, primary)
    accent: '#2fd6a0',
    accent2: '#1d7a5d',
    accentWeak: 'rgba(47,214,160,0.13)',

    // Rating colors (data — dot + label, never chrome fill)
    sfw: '#5ead84',
    sugg: '#cba85a',
    nsfw: '#d27a7a',
    unrated: '#868d98',
    star: '#cba85a',
    sfwWeak: 'rgba(94,173,132,.15)',
    suggWeak: 'rgba(203,168,90,.15)',
    nsfwWeak: 'rgba(210,122,122,.15)',
    negBg: '#2a1a1c',
    negLine: '#5d3338',

    // Disabled / inert (explicit colors, never opacity)
    disabledBg: '#16181d',
    disabledFore: '#565d68',
  },

  shadow: {
    // Deeper float against the near-black void; reserved for truly floating surfaces.
    pop: '0 24px 60px rgba(0,0,0,.65)',
    // Visible, on-brand jade focus ring (focus-visible only).
    focus: '0 0 0 3px rgba(47,214,160,.34)',
  },

  radius: {
    // Softer radius ramp: 8 / 9 / 12 / 16. `small`
    // is the sub-button radius (keycaps, segmented controls, inline-code, glyph),
    // a single source of truth.
    small: '8px',
    button: '9px',
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
    strong: 'rgba(5,6,8,.92)',
    soft: 'rgba(5,6,8,.45)',
  },

  font: {
    // ONE typeface app-wide: Schibsted Grotesk (clean, distinctive grotesk). The
    // `mono` token is the NUMERIC role but points at the SAME family — numerics
    // read tabular via the body `font-variant-numeric: tabular-nums` below. No
    // second font, no serif.
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
    tight: '-0.02em',
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

// Page-level defaults. The theme class is applied to <html> (done in main.tsx
// via themeStore.applyTheme()); these globals read the contract vars.
globalStyle('html, body, #root', {
  margin: 0,
  minHeight: '100%',
});

globalStyle('body', {
  backgroundColor: vars.color.void,
  color: vars.color.fore,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.body,
  lineHeight: vars.lineHeight.base,
  // Tabular figures app-wide so counts/columns align (Schibsted Grotesk supports
  // tnum). Right for a data-dense pro tool.
  fontVariantNumeric: 'tabular-nums',
  WebkitFontSmoothing: 'antialiased',
  textRendering: 'optimizeLegibility',
});

globalStyle('*, *::before, *::after', {
  boxSizing: 'border-box',
});

// Focus-ring floor (P1 mandate): every interactive element gets the on-brand
// ring on keyboard focus. focus-visible only, so mouse clicks stay quiet.
// Per-element overrides (e.g. tiles) may set their own boxShadow.
globalStyle(
  'button:focus-visible, a:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible, [tabindex]:focus-visible, [role="option"]:focus-visible, [role="button"]:focus-visible',
  {
    boxShadow: vars.shadow.focus,
    outline: 'none',
  },
);

// Jade selection so highlights stay on-brand.
globalStyle('::selection', {
  backgroundColor: vars.color.accentWeak,
  color: vars.color.fore,
});
