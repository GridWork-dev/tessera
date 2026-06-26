import { createTheme } from '@vanilla-extract/css';
import { vars } from '../contract.css';

/**
 * LIGHT — the one light preset, filling the same Pigment contract as the dark
 * themes (theme.css.ts). A near-white surface ramp (floor #f4f5f7, layered light
 * panels up to pure-white tiles), an inverted text ramp (near-black fore down to
 * a still-readable fore4), retuned shadows/scrims/weak tints, and the jade signal
 * kept as the brand — darkened to #0f9d74 so it clears UI contrast on light.
 *
 * Built from the Pigment value object with surface/text/accent/scrim/shadow
 * deltas only; rating colors and the structural tokens (radius/space/size/font/
 * motion) stay IDENTICAL across themes (rating semantics are data, not theme).
 *
 * WCAG AA (text on the surfaces it sits on — verified via a contrast check):
 *   fore  : 13.92–17.46  (void..active)        — AA-normal everywhere
 *   fore2 : 7.00–8.78    (void..active)         — AA-normal everywhere
 *   fore3 : 4.69–5.88                            — AA-normal on every surface
 *   fore4 : 4.35–5.45 ; ≥4.61 on void/sunken/panel/panel2/surface (where its
 *           micro-counts sit); only the `active` pressed-fill reads 4.35 (UI/
 *           large-text safe), never body.
 *   accent (#0f9d74): 3.16–3.45 on the surface ramp (UI/non-text contrast ≥3).
 *   onAccent (#ffffff) on accent fill: 3.45 (button-label / UI text).
 *
 * `color-scheme: light` (set on this class in themes/index.ts) makes native form
 * controls + scrollbars render light to match.
 */
export const lightClass = createTheme(vars, {
  color: {
    // Surfaces — near-white ramp (floor -> raised, pure-white tiles on top)
    void: '#f4f5f7',
    sunken: '#eceef1',
    panel: '#fbfcfd',
    panel2: '#f4f6f8',
    surface: '#ffffff',
    hover: '#eef0f3',
    active: '#e2e6ea',

    // Hairlines & borders — light, low-contrast dividers
    hair: '#e3e6ea',
    line: '#d6dae0',
    line2: '#c2c8d0',

    // Text — inverted near-black ramp
    fore: '#161a20',
    fore2: '#454b55',
    fore3: '#5e6570',
    fore4: '#646a73',
    onAccent: '#ffffff',

    // Jade signal accent — darkened for light surfaces (UI contrast >=3)
    accent: '#0f9d74',
    accent2: '#0c7d5d',
    accentWeak: 'rgba(15,157,116,0.12)',

    // Rating colors — kept consistent with the dark themes (data, never chrome),
    // but darkened just enough to read as label text on light surfaces.
    sfw: '#1f9d63',
    sugg: '#9a7320',
    nsfw: '#c43f3f',
    unrated: '#5e6570',
    star: '#9a7320',
    sfwWeak: 'rgba(31,157,99,.13)',
    suggWeak: 'rgba(154,115,32,.13)',
    nsfwWeak: 'rgba(196,63,63,.13)',
    negBg: '#fbe9ea',
    negLine: '#e6b3b8',

    // Disabled / inert (explicit colors, never opacity)
    disabledBg: '#eceef1',
    disabledFore: '#a3a9b2',
  },

  shadow: {
    // Softer, cooler float for light surfaces (a near-black 65% scrim would read
    // as a hard smudge on white).
    pop: '0 24px 60px rgba(20,24,32,.18)',
    // Jade focus ring, a touch stronger so it stays visible on bright surfaces.
    focus: '0 0 0 3px rgba(15,157,116,.30)',
  },

  radius: {
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
    // Light scrims dim toward a cool near-white so image chrome stays legible
    // without the heavy black wash the dark themes use.
    strong: 'rgba(244,245,247,.92)',
    soft: 'rgba(244,245,247,.55)',
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
