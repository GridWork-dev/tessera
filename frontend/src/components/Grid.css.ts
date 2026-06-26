import { keyframes, style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   Grid — justified-layout tiles with roving keyboard nav,
   bulk-select state, rating badge, and robust image loading.
   Co-located styles; reuses workspace.css for the container
   (gridInner) + base tile chrome where it composes cleanly.
   ============================================================ */

// Subtle pulse for the skeleton placeholder shown while a thumb loads.
const skeletonPulse = keyframes({
  '0%': { opacity: 0.6 },
  '50%': { opacity: 1 },
  '100%': { opacity: 0.6 },
});

const fadeIn = keyframes({
  from: { opacity: 0 },
  to: { opacity: 1 },
});

/** Removes the default focus outline on the listbox; focus is shown per-tile. */
export const listbox = style({
  outline: 'none',
});

/**
 * Tile button. We re-declare here (rather than reuse ws.tile) so the grid owns
 * its full interactive surface: focus-visible ring, selected ring, and a
 * keyboard-focused (roving) state distinct from pointer hover.
 */
export const tile = style({
  position: 'absolute',
  overflow: 'hidden',
  margin: 0,
  padding: 0,
  borderRadius: vars.radius.tile,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.hair}`,
  cursor: 'pointer',
  appearance: 'none',
  WebkitAppearance: 'none',
  transition: `box-shadow ${vars.motion.durFast} ${vars.motion.easeOut}, border-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { borderColor: vars.color.line2 },
    // Roving focus: the container manages tabindex, so the focused tile is the
    // one tab/arrow lands on. Mirror the global focus ring for keyboard users.
    '&:focus-visible': {
      outline: 'none',
      borderColor: vars.color.accent2,
      boxShadow: vars.shadow.focus,
    },
  },
});

/** Single-selected (inspector target) — accent ring. */
export const tileActive = style({
  borderColor: vars.color.accent,
  boxShadow: vars.shadow.focus,
});

/** Bulk-selected (multi-select triage) — solid accent ring + raised feel. */
export const tileChecked = style({
  borderColor: vars.color.accent,
  boxShadow: `0 0 0 2px ${vars.color.accent} inset`,
});

export const imgWrap = style({
  position: 'absolute',
  inset: 0,
  width: '100%',
  height: '100%',
});

/** Skeleton shimmer behind the thumb until it loads (or errors). */
export const skeleton = style({
  position: 'absolute',
  inset: 0,
  backgroundColor: vars.color.sunken,
  animation: `${skeletonPulse} 1.4s ${vars.motion.easeOut} infinite`,
});

export const img = style({
  position: 'absolute',
  inset: 0,
  width: '100%',
  height: '100%',
  objectFit: 'cover',
  display: 'block',
  opacity: 0,
});

/** Applied on load to fade the thumb in over the skeleton. */
export const imgLoaded = style({
  opacity: 1,
  animation: `${fadeIn} ${vars.motion.durBase} ${vars.motion.easeOut}`,
});

/** Fallback shown when a thumb 404s mid-pipeline. */
export const broken = style({
  position: 'absolute',
  inset: 0,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  backgroundColor: vars.color.sunken,
  color: vars.color.fore4,
});

/** Rating badge — TEXT label (never color-only) + a color dot. */
export const ratingBadge = style({
  position: 'absolute',
  top: vars.space['1'],
  left: vars.space['1'],
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
  height: '16px',
  padding: `0 ${vars.space['1.5']}`,
  borderRadius: vars.radius.pill,
  backgroundColor: vars.scrim.strong,
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  fontWeight: vars.fontWeight.med,
  letterSpacing: vars.letterSpacing.label,
  lineHeight: vars.lineHeight.tight,
  pointerEvents: 'none',
});

export const ratingDot = style({
  width: '6px',
  height: '6px',
  borderRadius: '50%',
  flexShrink: 0,
});

export const flagBadge = style({
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
  pointerEvents: 'none',
});

/** Multi-select checkmark — bottom-right so it never overlaps rating/flag. */
export const checkBadge = style({
  position: 'absolute',
  bottom: vars.space['1'],
  right: vars.space['1'],
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '18px',
  height: '18px',
  borderRadius: vars.radius.pill,
  backgroundColor: vars.color.accent,
  color: vars.color.onAccent,
  pointerEvents: 'none',
});
