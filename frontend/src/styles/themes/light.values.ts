/**
 * LIGHT theme token VALUES — a plain object (no vanilla-extract import) so it can
 * be consumed by `light.css.ts` (`createTheme`) AND imported directly by the
 * WCAG-AA contrast test (`light.contrast.test.ts`). The test runs under bare
 * vitest, which does NOT load the vanilla-extract plugin, so it cannot import a
 * `.css.ts`; keeping the raw values here is what makes the contract testable.
 *
 * Fills the same Pigment contract as the dark themes: a near-white surface ramp,
 * an inverted near-black text ramp, retuned shadows/scrims, and the jade signal
 * darkened so it clears WCAG AA on light surfaces. Rating colors are retuned for
 * the inverted ramp (data, not chrome — they must stay legible as label text).
 * Structural tokens (radius/space/size/font/motion) are IDENTICAL across themes.
 */
export const lightValues = {
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

    // Jade signal accent — darkened for light surfaces so the UI marker clears
    // 3:1 on every surface (incl. the `active`/`sunken` steps) AND white
    // `onAccent` clears 4.5:1 on the fill (full AA-normal button labels).
    accent: '#0c8462',
    accent2: '#0a6f53',
    accentWeak: 'rgba(12,132,98,0.12)',

    // Rating colors — retuned for the light ramp so each reads as AA-normal label
    // TEXT (>=4.5:1) on the primary surfaces, matching the dark themes' bar.
    sfw: '#13804a',
    sugg: '#876418',
    nsfw: '#c43f3f',
    unrated: '#5e6570',
    star: '#876418',
    sfwWeak: 'rgba(19,128,74,.13)',
    suggWeak: 'rgba(135,100,24,.13)',
    nsfwWeak: 'rgba(196,63,63,.13)',
    negBg: '#fbe9ea',
    negLine: '#e6b3b8',

    // Disabled / inert (explicit colors, never opacity). Exempt from AA per WCAG
    // 1.4.3 (disabled controls), so deliberately low-contrast to read as inert.
    disabledBg: '#eceef1',
    disabledFore: '#a3a9b2',
  },

  shadow: {
    // Softer, cooler float for light surfaces (a near-black 65% scrim would read
    // as a hard smudge on white).
    pop: '0 24px 60px rgba(20,24,32,.18)',
    // Jade focus ring, a touch stronger so it stays visible on bright surfaces.
    focus: '0 0 0 3px rgba(12,132,98,.30)',
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
};
