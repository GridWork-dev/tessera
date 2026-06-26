# Design

> Visual system for the Tessera DAM frontend. Theme name: **Pigment**.
> Source of truth for tokens: `frontend/src/styles/contract.css.ts` (shape) +
> `theme.css.ts` (values). Re-theming = swap values in `theme.css.ts` only.
> Reference mockup: `outputs/mockups/tessera/pigment.html`.

## Theme

Dark-only, "committed-signal." A near-black surface ramp (#0a0b0d floor) steps up to
quiet slate panels; ONE ownable jade signal (#2fd6a0) carries the brand — the lit
tessera you hunt for in the grid. Pro-tool neutral, decompressed for calm but dense
where the user scans (grid, filmstrip, facets). Color strategy: **restrained surface
+ one committed accent** — the jade is kept ≤10% of the surface (focus, the single
active marker, ⌘K, primary actions) so imagery + data dominate.

## Color

OKLCH-reasoned hex values, organized as a token ramp. WCAG AA verified (fore on void
17.3:1; fore3 4.99:1 on the lightest surface; accent 9.87:1 on panel; onAccent on
jade 10.2:1).

**Surfaces** (deep → raised)
- `void` `#0a0b0d` — app background, near-black floor
- `sunken` `#0e1013` — wells, inputs
- `panel` `#121419` — rails / panels
- `panel2` `#171a20` — panel headers, raised chrome
- `surface` `#1b1e25` — rows, chips, tiles (slate)
- `hover` `#242833` · `active` `#2f3540`

**Hairlines** — `hair` `#20242b` (default) · `line` `#262a32` (divider) · `line2` `#373d48` (control borders)

**Text** — `fore` `#eef0f4` (primary) · `fore2` `#abb1bd` (secondary) · `fore3` `#868d98` (tertiary/labels, AA-normal on every surface) · `fore4` `#828893` (faint micro-counts; AA-normal on void/sunken/panel/panel2) · `onAccent` `#04130d`

**Accent (jade signal, single)** — `accent` `#2fd6a0` · `accent2` `#1d7a5d` (border/dim) · `accentWeak` `rgba(47,214,160,.13)` (tint fill, focus ring)

**Rating colors (semantic data, never chrome)** — `sfw` `#5ead84` · `sugg` `#cba85a` · `nsfw` `#d27a7a` · `unrated` `#868d98` · `star` `#cba85a`; weak tints at .15 alpha; destructive `negBg` `#2a1a1c` / `negLine` `#5d3338`. Always paired with a label/shape, never color-only (color-blind safe).

## Brand mark & wordmark

**Mark = the Facet tessera** — a single jade tile (rounded square, fill `currentColor`
so it re-themes to the active accent) split on the diagonal into two facets by a
translucent-black hairline (reads on any accent). Rendered at 22px in the command
bar (`AppNav.tsx::BrandFacet`); app-icon (jade ground) / favicon variants scale down
to 16px cleanly. **Wordmark = "Tessera"** in Schibsted Grotesk 700, `-0.02em`. The
mark + wordmark form the top-left brand lockup of every command bar.

## Typography

**ONE clean grotesk for everything: Schibsted Grotesk.** Self-hosted via
@fontsource-variable (no CDN; local-first / privacy). A single distinctive display
face is intentionally avoided (it would fight the imagery; product register, not
brand). The wordmark uses the same family at weight 700.
- **Sans (UI + numerics + wordmark):** Schibsted Grotesk — `"Schibsted Grotesk Variable", -apple-system, "Segoe UI", Roboto, system-ui, sans-serif`
- **The `mono` token** is the NUMERIC role but aliases Schibsted Grotesk; dense numeric chrome (counts, confidences, dimensions, hashes, timestamps) reads tabular via the app-wide `font-variant-numeric: tabular-nums` — same family, no second font.

> Theme tokens are applied to `<html>` (`document.documentElement`, set in `main.tsx`)
> so the CSS vars resolve on `<body>` and any portaled content too — without this,
> off-theme elements fall back to the browser serif default.

**Type scale** — `micro` 11px (numeric chrome) · `label` 12px (uppercase sections) · `meta` 13px (secondary chrome, counts) · `heading` 14px (panel/section headings) · `body` 15px (base) · `brand` 18px.
**Weights** — 400 / 500 / 600 / 700. **Letter-spacing** — `label` .06em (uppercase), `tight` −0.02em (wordmark/display). **Line-height** — `tight` 1.2 (chrome), `snug` 1.35 (captions), `base` 1.5 (body).

## Spacing & Layout

4pt scale: `1`=4 · `2`=8 · `3`=12 · `4`=16 · `5`=24 · `6`=32 · `7`=48 · `8`=64 · `9`=96 px. Prefer `gap` over `margin`. Density knob: `rowH` 38px (comfortable) / `rowHDense` 30px (compact); command `barH` 60px.

**App layout — 3-zone workspace** (Clean Dense Pro-DAM):
- **Command bar** (top) — brand lockup + global search + ⌘K palette.
- **Left facet rail** — collapsible filter facets with disjunctive counts.
- **Center grid** — virtualized justified dense thumbnail grid (TanStack Virtual + justified-layout).
- **Right inspector** — per-asset metadata (tags, rating, captions, similar).
- **Filmstrip** (bottom, contextual) + **docked lightbox** for focused review.

Flexbox for 1D chrome, Grid for 2D. No cards-by-reflex; the grid is the content.

## Geometry & Elevation

Radii (softer than the prior ramp) — `small` 8px (keycaps, segmented controls, inline-code, brand glyph), `button` 9px (buttons/chips), `tile` 12px (grid tiles), `panel` 16px (cards/panels), `pill` 999px. Values mirror `theme.css.ts` (single source of truth); regenerate this section via `/impeccable document` after token changes. Shadow — `pop` `0 24px 60px rgba(0,0,0,.65)` (floating: lightbox, command bar, popovers). Focus — `focus` `0 0 0 3px rgba(47,214,160,.34)` (jade), on every interactive element. Scrims — `strong` `rgba(5,6,8,.92)` (legible image chrome), `soft` `rgba(5,6,8,.45)`.

## Motion

Restrained and functional. Ease-out (quart/quint), no bounce/elastic. Animate transform/opacity (and blur/backdrop where it earns it), not layout. Staggered list entrances are fine; no uniform whole-page reveal reflex. Every transition has a `prefers-reduced-motion: reduce` fallback (crossfade or instant). Reveals enhance already-visible content — never gate visibility on a transition. Durations: `durFast` 120ms (hover/color), `durBase` 180ms (inspector slide).

## Iconography

`lucide-react`, line icons, sized to the text they sit with (typically 16–20px), `aria-hidden` when decorative. Icon color follows text level or accent; never multicolor.

## Implementation

Zero-runtime tokens via **vanilla-extract**: `createThemeContract` (shape) + `createTheme` (values) → `themeClass` (Pigment) applied at `<html>`. Two alternate dark themes (`slate-warm`, `obsidian-cool`) are separate `createTheme` files selectable via the Settings → Appearance switcher; Pigment is the default. Components reference `vars.*` for compile-time-checked tokens. Recipes (`@vanilla-extract/recipes`) for variant-driven components. Biome for lint/format; React 19 + React Compiler; Vite.
