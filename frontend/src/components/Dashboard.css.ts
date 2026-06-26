import { keyframes, style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   Dashboard — landing surface + live monitoring.

   Full-viewport vertically-scrollable surface (Browse locks the
   body; this does not). Clean instrument panels on `panel` with
   hairline borders; the single restrained accent is reserved for
   live progress fills, meters, and the running pulse. No hero
   metric (no giant number + tiny uppercase label + glow), no
   gradient, no glassmorphism, no decorative side-stripes.

   Co-located styles; tokens only (no hardcoded hex / px fonts).
   Motion via vars.motion.*; the global prefers-reduced-motion
   rule in workspace.css already collapses these animations.
   ============================================================ */

/* Scrolling content region under the shared command bar. Browse locks the body;
   the dashboard scrolls. appFrame (workspace.css) owns the viewport + header. */
export const scroll = style({
  flex: 1,
  minHeight: 0,
  overflowY: 'auto',
  overflowX: 'hidden',
  backgroundColor: vars.color.void,
  color: vars.color.fore,
  fontFamily: vars.font.sans,
});

export const inner = style({
  maxWidth: '1180px',
  margin: '0 auto',
  padding: `${vars.space['6']} ${vars.space['5']} ${vars.space['8']}`,
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['6'],
});

/* ---- Section scaffolding ---- */

export const section = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['3'],
});

// Sentence-case section heads (uppercase reserved for top-level zone headers).
export const sectionHead = style({
  display: 'flex',
  alignItems: 'baseline',
  justifyContent: 'space-between',
  gap: vars.space['3'],
});

export const sectionTitle = style({
  fontSize: vars.fontSize.heading,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore,
});

export const sectionMeta = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  whiteSpace: 'nowrap',
});

export const panel = style({
  backgroundColor: vars.color.panel,
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.panel,
  padding: vars.space['4'],
});

/* ============================================================
   Pipeline tiers — one horizontal progress bar per tier
   ============================================================ */

export const tierList = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['4'],
});

export const tierRow = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const tierHead = style({
  display: 'flex',
  alignItems: 'baseline',
  justifyContent: 'space-between',
  gap: vars.space['3'],
});

export const tierName = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['2'],
  fontSize: vars.fontSize.meta,
  color: vars.color.fore2,
});

export const tierCounts = style({
  display: 'inline-flex',
  alignItems: 'baseline',
  gap: vars.space['2'],
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore3,
  fontVariantNumeric: 'tabular-nums',
  textAlign: 'right',
  whiteSpace: 'nowrap',
});

export const tierPct = style({
  color: vars.color.fore,
  fontWeight: vars.fontWeight.med,
});

/* Track + accent fill. */
export const track = style({
  position: 'relative',
  width: '100%',
  height: '8px',
  backgroundColor: vars.color.surface,
  borderRadius: vars.radius.pill,
  overflow: 'hidden',
});

// Compositor-only fill: width is 100% and the pct is applied inline as
// transform: scaleX(fraction) from the left edge — no layout thrash.
export const fill = style({
  position: 'absolute',
  insetBlock: 0,
  left: 0,
  width: '100%',
  transformOrigin: 'left center',
  backgroundColor: vars.color.accent,
  borderRadius: vars.radius.pill,
  transition: `transform ${vars.motion.durBase} ${vars.motion.easeOut}`,
});

/* ---- Running pulse dot ---- */

const pulse = keyframes({
  '0%': { opacity: 1, transform: 'scale(1)' },
  '50%': { opacity: 0.3, transform: 'scale(0.7)' },
  '100%': { opacity: 1, transform: 'scale(1)' },
});

export const dot = style({
  width: '7px',
  height: '7px',
  borderRadius: '50%',
  flexShrink: 0,
});

export const dotRunning = style({
  backgroundColor: vars.color.accent,
  animation: `${pulse} 1.6s ${vars.motion.easeOut} infinite`,
});

export const dotIdle = style({
  backgroundColor: vars.color.line2,
});

export const runningTag = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.accent,
});

/* ============================================================
   System instruments
   ============================================================ */

export const statGrid = style({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
  gap: vars.space['4'],
});

export const stat = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const statHead = style({
  display: 'flex',
  alignItems: 'baseline',
  justifyContent: 'space-between',
  gap: vars.space['2'],
});

export const statLabel = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
});

export const statValue = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore,
  fontVariantNumeric: 'tabular-nums',
  textAlign: 'right',
  whiteSpace: 'nowrap',
});

export const statSub = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  fontVariantNumeric: 'tabular-nums',
  textAlign: 'right',
  whiteSpace: 'nowrap',
});

/* Thin meter for CPU / RAM / Disk. */
export const meterTrack = style({
  position: 'relative',
  width: '100%',
  height: '6px',
  backgroundColor: vars.color.surface,
  borderRadius: vars.radius.pill,
  overflow: 'hidden',
});

// Compositor-only: width 100%, pct applied inline as transform: scaleX(fraction).
export const meterFill = style({
  position: 'absolute',
  insetBlock: 0,
  left: 0,
  width: '100%',
  transformOrigin: 'left center',
  backgroundColor: vars.color.accent,
  borderRadius: vars.radius.pill,
  transition: `transform ${vars.motion.durBase} ${vars.motion.easeOut}`,
});

/* Per-core mini bars. */
export const cores = style({
  display: 'flex',
  alignItems: 'flex-end',
  gap: vars.space['0.5'],
  height: '24px',
});

// Compositor-only: full height, per-core load applied inline as
// transform: scaleY(fraction) growing from the bottom edge.
export const core = style({
  flex: 1,
  minWidth: '2px',
  height: '100%',
  transformOrigin: 'bottom center',
  backgroundColor: vars.color.accent2,
  transition: `transform ${vars.motion.durFast} ${vars.motion.easeOut}`,
});

/* ---- Inline misc rows (load avg / gpu / tagger) ---- */

export const inlineRows = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['1'],
});

export const inlineRow = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: vars.space['3'],
  minHeight: vars.size.rowHDense,
});

export const inlineKey = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['2'],
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
});

export const inlineVal = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore,
  fontVariantNumeric: 'tabular-nums',
  textAlign: 'right',
  whiteSpace: 'nowrap',
});

/* Small status chip (GPU backend / tagger). Accent only when active. */
export const statusChip = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1'],
  fontSize: vars.fontSize.micro,
  fontWeight: vars.fontWeight.med,
  padding: `${vars.space['0.5']} ${vars.space['2']}`,
  borderRadius: vars.radius.pill,
  border: `1px solid ${vars.color.hair}`,
  backgroundColor: vars.color.sunken,
  color: vars.color.fore3,
});

export const statusChipOk = style({
  color: vars.color.accent,
  borderColor: vars.color.accent2,
  backgroundColor: vars.color.accentWeak,
});

/* ============================================================
   Throughput
   ============================================================ */

export const throughput = style({
  display: 'flex',
  alignItems: 'baseline',
  gap: vars.space['3'],
  flexWrap: 'wrap',
});

export const throughputNum = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.display,
  fontWeight: vars.fontWeight.med,
  color: vars.color.fore,
  fontVariantNumeric: 'tabular-nums',
  lineHeight: vars.lineHeight.tight,
});

export const throughputUnit = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
});

export const throughputMeta = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  fontVariantNumeric: 'tabular-nums',
});

/* ============================================================
   Library overview — summary + per-person table
   ============================================================ */

export const summaryRow = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space['6'],
  marginBottom: vars.space['4'],
});

export const summaryItem = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['1'],
});

export const summaryLabel = style({
  fontSize: vars.fontSize.label,
  color: vars.color.fore3,
});

export const summaryNum = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.display,
  fontWeight: vars.fontWeight.med,
  color: vars.color.fore,
  fontVariantNumeric: 'tabular-nums',
  letterSpacing: vars.letterSpacing.tight,
});

export const tableScroll = style({
  overflowX: 'auto',
});

export const table = style({
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: vars.fontSize.meta,
});

export const th = style({
  textAlign: 'left',
  padding: `${vars.space['2']} ${vars.space['3']}`,
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore3,
  borderBottom: `1px solid ${vars.color.line}`,
  whiteSpace: 'nowrap',
});

export const thNum = style({
  textAlign: 'right',
});

export const td = style({
  padding: `${vars.space['2']} ${vars.space['3']}`,
  borderBottom: `1px solid ${vars.color.hair}`,
  color: vars.color.fore2,
  verticalAlign: 'middle',
});

export const tdKey = style({
  color: vars.color.fore,
  fontWeight: vars.fontWeight.med,
  textTransform: 'capitalize',
  whiteSpace: 'nowrap',
});

export const tdNum = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore,
  fontVariantNumeric: 'tabular-nums',
  textAlign: 'right',
  whiteSpace: 'nowrap',
});

export const tdMuted = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  fontVariantNumeric: 'tabular-nums',
  textAlign: 'right',
  whiteSpace: 'nowrap',
});

/* Rating breakdown cell: small RatingChips with mono counts beside them. */
export const ratingCell = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space['2'],
  justifyContent: 'flex-end',
});

export const ratingPair = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
});

export const ratingPairCount = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore3,
  fontVariantNumeric: 'tabular-nums',
});

/* ============================================================
   Exclude/hide suggestions (mined from rejects)
   ============================================================ */

export const suggestList = style({
  display: 'flex',
  flexDirection: 'column',
});

export const suggestRow = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  minHeight: vars.size.rowH,
  padding: `${vars.space['2']} 0`,
  borderBottom: `1px solid ${vars.color.hair}`,
  selectors: { '&:last-child': { borderBottom: 'none' } },
});

export const suggestTag = style({
  flex: 1,
  minWidth: 0,
  display: 'flex',
  alignItems: 'baseline',
  gap: vars.space['2'],
  fontSize: vars.fontSize.meta,
  color: vars.color.fore,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const suggestCat = style({
  fontSize: vars.fontSize.label,
  color: vars.color.fore3,
  textTransform: 'capitalize',
});

export const suggestCount = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  fontVariantNumeric: 'tabular-nums',
  whiteSpace: 'nowrap',
});

export const hideBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['2'],
  height: vars.size.controlSm,
  padding: `0 ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line2}`,
  backgroundColor: vars.color.surface,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  cursor: 'pointer',
  flexShrink: 0,
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:disabled': { opacity: 0.5, cursor: 'default' },
  },
});

export const reasonChips = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space['2'],
  marginTop: vars.space['3'],
});

export const reasonChip = style({
  display: 'inline-flex',
  alignItems: 'baseline',
  gap: vars.space['1'],
  padding: `${vars.space['0.5']} ${vars.space['2']}`,
  borderRadius: vars.radius.pill,
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.hair}`,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore3,
});

/* ============================================================
   States (loading / error / inline)
   ============================================================ */

export const stateInline = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  color: vars.color.fore3,
  fontSize: vars.fontSize.meta,
});

export const errorInline = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  color: vars.color.sugg,
  fontSize: vars.fontSize.meta,
});

const shimmer = keyframes({
  '0%': { opacity: 0.55 },
  '50%': { opacity: 0.85 },
  '100%': { opacity: 0.55 },
});

export const skeleton = style({
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.panel,
  height: '120px',
  animation: `${shimmer} 1.6s ${vars.motion.easeOut} infinite`,
});
