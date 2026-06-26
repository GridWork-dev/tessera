import { createThemeContract } from '@vanilla-extract/css';

/**
 * Typed token contract — the SHAPE of the design system.
 *
 * Declares which tokens exist (and gives them stable CSS-var names); the actual
 * VALUES live in `theme.css.ts`. Components reference `vars.color.*` /
 * `vars.space.*` / etc. and get compile-time autocomplete + "token does not
 * exist" errors under strict TS.
 *
 * Token NAMES + grouping mirror the Pigment design system (DESIGN.md): a
 * near-black surface ramp, one committed jade signal accent, semantic rating
 * colors used as data (never chrome). Typeface = Schibsted Grotesk (one family),
 * self-hosted. Re-theming = swap VALUES in theme.css.ts; this shape stays stable.
 */
export const vars = createThemeContract({
  color: {
    // Surfaces — cool Pigment surface ramp, low-contrast steps (deep -> raised)
    void: null, // app background, deepest surface
    sunken: null, // sunken wells, inputs
    panel: null, // rails / panels
    panel2: null, // panel headers, raised chrome
    surface: null, // rows, chips, tiles (slate)
    hover: null, // hover state
    active: null, // pressed / selected fill

    // Hairlines & borders
    hair: null, // default hairline
    line: null, // stronger divider
    line2: null, // control borders

    // Text (4 levels + on-accent)
    fore: null, // primary text
    fore2: null, // secondary text
    fore3: null, // tertiary / labels
    fore4: null, // faint / decorative micro-counts
    onAccent: null, // text on accent fills

    // Single restrained accent (jade)
    accent: null,
    accent2: null, // accent border / dim
    accentWeak: null, // accent tint fill

    // Semantic rating colors (data, not chrome)
    sfw: null,
    sugg: null,
    nsfw: null,
    unrated: null,
    star: null,
    sfwWeak: null,
    suggWeak: null,
    nsfwWeak: null,
    negBg: null, // destructive surface
    negLine: null, // destructive border

    // Disabled / inert controls (explicit, never opacity)
    disabledBg: null,
    disabledFore: null,
  },

  shadow: {
    pop: null, // floating panels (lightbox, command bar, popovers)
    focus: null, // focus ring
  },

  radius: {
    small: null, // tiny chrome: keycaps, segmented buttons, inline-code, glyph
    button: null, // buttons / chips
    panel: null, // cards / panels (floating)
    tile: null, // grid tiles (tighter than panels)
    pill: null, // fully rounded
  },

  // 4pt spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96
  space: {
    '0.5': null, // 2px half-step
    '1': null,
    '1.5': null, // 6px half-step
    '2': null,
    '3': null,
    '4': null,
    '5': null,
    '6': null,
    '7': null,
    '8': null,
    '9': null,
  },

  size: {
    controlXs: null, // 24px
    controlSm: null, // 28px
    controlMd: null, // 32px
    controlLg: null, // 38px
    rowH: null, // facet/list row height — comfortable / in-depth default
    rowHDense: null, // facet/list row height — basic / compact density
    barH: null, // command-bar height
  },

  scrim: {
    strong: null, // image-chrome overlay (legible)
    soft: null, // subtle dim
  },

  font: {
    sans: null, // Schibsted Grotesk — the single UI typeface (all text)
    mono: null, // numeric role — aliases Schibsted Grotesk; tabular via font-variant-numeric
  },

  fontSize: {
    micro: null, // 11px dense numeric chrome (mono)
    label: null, // 12px section labels
    meta: null, // 13px secondary chrome, counts
    heading: null, // 14px panel / section headings
    body: null, // 15px base body (Geist reads larger; AA-safe for UI)
    brand: null, // 18px brand mark
    display: null, // 20px page titles / dashboard headings (used sparingly)
  },

  fontWeight: {
    reg: null,
    med: null,
    semi: null,
    bold: null,
  },

  letterSpacing: {
    label: null, // section labels
    tight: null, // wordmark / display (slightly negative)
  },

  lineHeight: {
    tight: null, // dense chrome
    snug: null, // multi-line captions
    base: null, // body
  },

  motion: {
    durFast: null, // hover / color crossfades
    durBase: null, // inspector slide, larger transitions
    easeOut: null, // exponential ease-out (no bounce)
  },
});
