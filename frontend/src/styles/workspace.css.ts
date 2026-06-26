import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from './contract.css';

/* ============================================================
   App frame — full viewport, no body scroll. Command bar on top,
   3-zone workspace below (rail / grid / inspector).
   ============================================================ */

export const appFrame = style({
  display: 'flex',
  flexDirection: 'column',
  height: '100vh',
  overflow: 'hidden',
  backgroundColor: vars.color.void,
});

export const body = style({
  flex: 1,
  minHeight: 0,
  display: 'grid',
  gridTemplateColumns: `280px minmax(0, 1fr) 360px`,
  overflow: 'hidden',
  '@media': {
    // Desktop-first product (PRODUCT.md). Two staged collapses so the center
    // grid never gets crushed:
    //   • ≤1024px (tablet): drop the 360px inspector column — the inspector
    //     hides at the same breakpoint — leaving rail + grid a workable width.
    //   • ≤760px (phone): collapse to a single column; rail + inspector both
    //     hide so the asset grid fills the viewport and nothing clips off-screen.
    '(max-width: 1024px)': { gridTemplateColumns: '280px minmax(0, 1fr)' },
    '(max-width: 760px)': { gridTemplateColumns: 'minmax(0, 1fr)' },
  },
});

export const bodyNoInspector = style({
  gridTemplateColumns: `280px minmax(0, 1fr)`,
  '@media': {
    '(max-width: 760px)': { gridTemplateColumns: 'minmax(0, 1fr)' },
  },
});

/* ---- Command bar ---- */

export const commandBar = style({
  display: 'flex',
  alignItems: 'center',
  // Wrap (don't clip) when the brand + nav + search + right cluster exceed the
  // viewport — a fixed-height non-wrapping row pushed controls off-screen on
  // narrow windows. `gap` supplies the row gap when items wrap; `minHeight`
  // (not a fixed height) lets the bar grow to fit the wrapped rows.
  flexWrap: 'wrap',
  gap: vars.space['3'],
  minHeight: vars.size.barH,
  flexShrink: 0,
  padding: `${vars.space['2']} ${vars.space['5']}`,
  backgroundColor: vars.color.panel2,
  borderBottom: `1px solid ${vars.color.hair}`,
});

export const brand = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  color: vars.color.fore,
  fontSize: vars.fontSize.brand,
  fontWeight: vars.fontWeight.bold,
  letterSpacing: vars.letterSpacing.tight,
  textDecoration: 'none',
  userSelect: 'none',
});

export const brandIcon = style({ color: vars.color.accent });

export const searchWrap = style({
  position: 'relative',
  flex: 1,
  maxWidth: '560px',
});

export const searchInput = style({
  width: '100%',
  height: '42px',
  padding: `0 ${vars.space['3']} 0 38px`,
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore,
  fontSize: vars.fontSize.heading,
  fontFamily: vars.font.sans,
  outline: 'none',
  transition: `border-color ${vars.motion.durFast} ${vars.motion.easeOut}, box-shadow ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&::placeholder': { color: vars.color.fore3 },
    '&:focus': { borderColor: vars.color.accent2, boxShadow: vars.shadow.focus },
  },
});

export const searchIcon = style({
  position: 'absolute',
  left: vars.space['3'],
  top: '50%',
  transform: 'translateY(-50%)',
  color: vars.color.fore3,
  pointerEvents: 'none',
});

export const kbdHint = style({
  position: 'absolute',
  right: vars.space['2'],
  top: '50%',
  transform: 'translateY(-50%)',
  display: 'flex',
  gap: vars.space['0.5'],
  pointerEvents: 'none',
});

export const kbd = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore3,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.small,
  padding: `1px ${vars.space['1.5']}`,
  lineHeight: vars.lineHeight.tight,
});

export const barSpacer = style({ flex: 1 });

export const barMeta = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  whiteSpace: 'nowrap',
});

export const barCount = style({ color: vars.color.fore2 });

/* Page title + meta for command bars that aren't the Browse search bar
   (Dashboard, Videos). Sits right after the shared nav; meta is pushed right
   with barSpacer. Keeps every page's header on one consistent row. */
export const pageTitle = style({
  fontSize: vars.fontSize.heading,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore,
  letterSpacing: vars.letterSpacing.tight,
  whiteSpace: 'nowrap',
  marginLeft: vars.space['1'],
});

export const pageMeta = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  whiteSpace: 'nowrap',
  fontVariantNumeric: 'tabular-nums',
});

/* ---- Generic icon button ----
   The single app-wide square icon-button vocabulary. Shared by AppNav and the
   CommandBar right cluster (CommandBar re-exports this; it previously kept a
   divergent 34px-vs-32px copy without :active/:disabled). Full state set:
   hover, active (pressed), focus-visible ring, and explicit disabled. */

export const iconButton = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '32px',
  height: vars.size.controlMd,
  color: vars.color.fore3,
  backgroundColor: 'transparent',
  border: `1px solid transparent`,
  borderRadius: vars.radius.button,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:active:not(:disabled)': { backgroundColor: vars.color.active, color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
    '&:disabled': { color: vars.color.disabledFore, cursor: 'not-allowed' },
  },
  '@media': {
    // On coarse (touch) pointers these become the primary nav: grow them to the
    // 44px WCAG 2.5.5 / Apple HIG minimum tap target. Fine-pointer (mouse) stays
    // at the calm 32px desktop chrome size.
    '(pointer: coarse)': { width: '44px', height: '44px' },
  },
});

export const iconButtonActive = style({
  color: vars.color.accent,
  backgroundColor: vars.color.accentWeak,
});

/* ============================================================
   Facet rail (left)
   ============================================================ */

export const rail = style({
  borderRight: `1px solid ${vars.color.hair}`,
  backgroundColor: vars.color.panel,
  overflowY: 'auto',
  overflowX: 'hidden',
  paddingBottom: vars.space['6'],
  // Facets are a desktop affordance; hide the rail on phones so the grid owns
  // the full width (the body grid collapses to one column at the same breakpoint).
  '@media': {
    '(max-width: 760px)': { display: 'none' },
  },
});

export const railHeader = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  position: 'sticky',
  top: 0,
  zIndex: 1,
  padding: `${vars.space['3']} ${vars.space['4']}`,
  backgroundColor: vars.color.panel,
  borderBottom: `1px solid ${vars.color.hair}`,
});

export const railHeaderTitle = style({
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.semi,
  letterSpacing: vars.letterSpacing.label,
  textTransform: 'uppercase',
  color: vars.color.fore3,
});

export const clearBtn = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  color: vars.color.accent,
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  padding: 0,
  selectors: { '&:hover': { textDecoration: 'underline' } },
});

export const section = style({ borderBottom: `1px solid ${vars.color.hair}` });

// Facet-group labels (People, Clothing, …): sentence-case, calm. Uppercase is
// reserved for the two top-level zone headers (rail "Filters", inspector
// "Inspector") so the rail doesn't read as an eyebrow wall.
export const sectionLabel = style({
  display: 'block',
  padding: `${vars.space['4']} ${vars.space['4']} ${vars.space['2']}`,
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.semi,
  textTransform: 'capitalize',
  color: vars.color.fore3,
});

export const facetRow = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  width: '100%',
  minHeight: vars.size.rowH,
  padding: `0 ${vars.space['4']}`,
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  textAlign: 'left',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore },
  },
});

// The single, unmistakable "this filter is on" marker: accent tint + a 3px inset
// bar. A functional active-state indicator (not a decorative side-stripe) — keep
// it the only place this combination appears.
export const facetRowActive = style({
  backgroundColor: vars.color.accentWeak,
  color: vars.color.fore,
  boxShadow: `inset 3px 0 0 ${vars.color.accent}`,
});

export const facetName = style({
  flex: 1,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const facetCount = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  fontVariantNumeric: 'tabular-nums',
});

/* ============================================================
   Grid region (center)
   ============================================================ */

export const gridRegion = style({
  position: 'relative',
  // Fill the remaining height when it's a direct flex child of the app frame
  // (pages with no facet rail: Places, Events, People-disabled) so empty/loading
  // states center in the full content region instead of collapsing to a narrow
  // top strip. Ignored when it's a grid cell inside `body` (Browse/Videos).
  flex: '1 1 auto',
  minHeight: 0,
  overflowY: 'auto',
  overflowX: 'hidden',
  backgroundColor: vars.color.void,
});

export const gridInner = style({
  position: 'relative',
  margin: '0 auto',
  padding: vars.space['3'],
});

export const tile = style({
  position: 'absolute',
  overflow: 'hidden',
  borderRadius: vars.radius.tile,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.hair}`,
  cursor: 'pointer',
  transition: `box-shadow ${vars.motion.durFast} ${vars.motion.easeOut}, border-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { borderColor: vars.color.line2 },
  },
});

export const tileSelected = style({
  borderColor: vars.color.accent,
  boxShadow: vars.shadow.focus,
});

export const tileImg = style({
  width: '100%',
  height: '100%',
  objectFit: 'cover',
  display: 'block',
  backgroundColor: vars.color.sunken,
});

export const tileBadge = style({
  position: 'absolute',
  top: vars.space['1'],
  left: vars.space['1'],
  display: 'inline-flex',
  alignItems: 'center',
  height: '16px',
  padding: `0 ${vars.space['1.5']}`,
  borderRadius: vars.radius.pill,
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  fontWeight: vars.fontWeight.med,
  letterSpacing: vars.letterSpacing.label,
  textTransform: 'uppercase',
  backgroundColor: vars.scrim.strong,
});

export const tileFlag = style({
  position: 'absolute',
  top: vars.space['1'],
  right: vars.space['1'],
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '18px',
  height: '18px',
  borderRadius: vars.radius.pill,
  backgroundColor: vars.scrim.strong,
  color: vars.color.sugg,
});

/* ============================================================
   Inspector (right)
   ============================================================ */

export const inspector = style({
  borderLeft: `1px solid ${vars.color.hair}`,
  backgroundColor: vars.color.panel,
  overflowY: 'auto',
  display: 'flex',
  flexDirection: 'column',
  // Hidden ≤1024px (see `body`): the docked inspector needs width tablets/phones
  // don't have, and the body grid drops its column at the same breakpoint. On
  // these viewports a tile tap routes to the lightbox (which carries the same
  // keep/maybe/reject triage) so selection still has an action path.
  '@media': {
    '(max-width: 1024px)': { display: 'none' },
  },
});

export const inspectorHeader = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  position: 'sticky',
  top: 0,
  zIndex: 1,
  padding: `${vars.space['3']} ${vars.space['4']}`,
  backgroundColor: vars.color.panel,
  borderBottom: `1px solid ${vars.color.hair}`,
});

export const inspectorTitle = style({
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.semi,
  letterSpacing: vars.letterSpacing.label,
  textTransform: 'uppercase',
  color: vars.color.fore3,
});

export const inspectorPreview = style({
  width: '100%',
  aspectRatio: '1 / 1',
  objectFit: 'contain',
  backgroundColor: vars.color.sunken,
  borderBottom: `1px solid ${vars.color.hair}`,
});

export const inspectorBody = style({
  padding: vars.space['4'],
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['4'],
});

export const metaGrid = style({
  display: 'grid',
  gridTemplateColumns: 'auto 1fr',
  gap: `${vars.space['2']} ${vars.space['3']}`,
  alignItems: 'baseline',
});

export const metaKey = style({
  fontSize: vars.fontSize.label,
  textTransform: 'capitalize',
  color: vars.color.fore3,
});

export const metaVal = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore,
  overflowWrap: 'anywhere',
});

export const groupLabel = style({
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.semi,
  textTransform: 'capitalize',
  color: vars.color.fore3,
  marginBottom: vars.space['2'],
});

export const chipWrap = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space['1'],
});

export const chip = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1.5'],
  height: '22px',
  padding: `0 ${vars.space['2']}`,
  borderRadius: vars.radius.button,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.hair}`,
  color: vars.color.fore2,
  fontSize: vars.fontSize.micro,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: { '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore } },
});

export const chipConf = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  selectors: {
    // On chip hover the background lifts to `hover` (#242833), where fore4 drops
    // to 4.1:1 (below AA). Lift the confidence text to fore2 so it clears 4.5:1
    // in the hovered state too.
    [`${chip}:hover &`]: { color: vars.color.fore2 },
  },
});

/* ============================================================
   Rating chip (shared) + states
   ============================================================ */

export const ratingChip = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1.5'],
  height: '20px',
  padding: `0 ${vars.space['2']}`,
  borderRadius: vars.radius.pill,
  fontSize: vars.fontSize.micro,
  fontWeight: vars.fontWeight.med,
  letterSpacing: vars.letterSpacing.label,
  textTransform: 'uppercase',
});

export const ratingDot = style({
  width: '6px',
  height: '6px',
  borderRadius: '50%',
});

/* ---- States (empty / loading / error) ---- */

export const stateWrap = style({
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space['2'],
  height: '100%',
  padding: vars.space['6'],
  textAlign: 'center',
  color: vars.color.fore3,
});

export const stateTitle = style({
  fontSize: vars.fontSize.body,
  fontWeight: vars.fontWeight.med,
  color: vars.color.fore2,
});

export const stateHint = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore4,
  maxWidth: '34ch',
  lineHeight: vars.lineHeight.base,
});

/* ---- Inline degrade hint (e.g. semantic pending → tag matches) ---- */

export const degradedHint = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  margin: `0 ${vars.space['4']}`,
  padding: `${vars.space['2']} ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.line}`,
  color: vars.color.fore3,
  fontSize: vars.fontSize.meta,
  lineHeight: vars.lineHeight.base,
});

/* ---- Pagination footer ---- */

export const pager = style({
  position: 'sticky',
  bottom: 0,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space['3'],
  padding: vars.space['2'],
  backgroundColor: vars.scrim.strong,
  borderTop: `1px solid ${vars.color.hair}`,
});

export const pageBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1.5'],
  height: vars.size.controlSm,
  padding: `0 ${vars.space['3']}`,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
  fontFamily: vars.font.sans,
  cursor: 'pointer',
  selectors: {
    '&:hover:not(:disabled)': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:disabled': {
      backgroundColor: vars.color.disabledBg,
      color: vars.color.disabledFore,
      borderColor: vars.color.hair,
      cursor: 'default',
    },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});

export const pageInfo = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  minWidth: '120px',
  textAlign: 'center',
});

/* Reduced-motion: collapse all transitions/animations. */
globalStyle('*, *::before, *::after', {
  '@media': {
    '(prefers-reduced-motion: reduce)': {
      transitionDuration: '0.01ms !important',
      animationDuration: '0.01ms !important',
      animationIterationCount: '1 !important',
    },
  },
});
