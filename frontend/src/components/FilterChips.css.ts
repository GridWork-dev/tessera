import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   FilterChips — sticky active-filter strip at the top of the
   grid region. A removable chip per active filter, a "Clear all"
   action, and the mono result count (right-aligned).
   ============================================================ */

export const strip = style({
  position: 'sticky',
  top: 0,
  zIndex: 2,
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  minHeight: vars.size.rowH,
  padding: `${vars.space['2']} ${vars.space['3']}`,
  backgroundColor: vars.color.panel2,
  borderBottom: `1px solid ${vars.color.hair}`,
});

// Wraps the active-filter chips; flexes to absorb the row width so the
// count + clear action sit at the right.
export const chips = style({
  display: 'flex',
  flexWrap: 'wrap',
  alignItems: 'center',
  gap: vars.space['2'],
  flex: 1,
  minWidth: 0,
});

// A single removable filter chip. The body shows the filter; the × button
// is the removal affordance.
export const chip = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1.5'],
  height: vars.size.controlXs,
  paddingLeft: vars.space['2'],
  paddingRight: vars.space['1'],
  borderRadius: vars.radius.button,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.hair}`,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  whiteSpace: 'nowrap',
  maxWidth: '100%',
  minWidth: 0,
});

// Label text inside a chip — truncates rather than overflowing the strip.
export const chipText = style({
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  minWidth: 0,
});

// Dim "kind" prefix ("person", "tag", "status") so the value reads as primary.
export const chipKind = style({
  color: vars.color.fore3,
});

// The × button that removes a single filter.
export const remove = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  flexShrink: 0,
  width: '18px',
  height: '18px',
  padding: 0,
  border: 'none',
  background: 'none',
  borderRadius: vars.radius.button,
  color: vars.color.fore3,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});

// Rating chip variant — the RatingChip span carries its own color/label, so
// this shell stays neutral and just hosts the × button beside it.
export const ratingChip = style({
  gap: vars.space['1'],
});

// Right-aligned area: result count (mono) + clear-all action.
export const right = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  flexShrink: 0,
  marginLeft: 'auto',
});

export const count = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore2,
  whiteSpace: 'nowrap',
  fontVariantNumeric: 'tabular-nums',
});

// Muted while a fetch is in flight — the count is stale, not gone.
export const countLoading = style({
  color: vars.color.fore4,
});

export const clearAll = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  color: vars.color.accent,
  background: 'none',
  border: 'none',
  padding: 0,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
  selectors: {
    '&:hover': { textDecoration: 'underline' },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});
