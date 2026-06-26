import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   Videos — page chrome (command bar, body layout, facet rail,
   empty/loading states) is the SHARED workspace vocabulary
   (workspace.css), identical to Browse. This file owns only the
   video-specific surfaces: the poster card grid + the player
   modal with scene chips.
   ============================================================ */

/* Padding wrapper inside the shared gridRegion (which has no padding itself —
   Browse's justified grid positions absolutely; the video grid flows). */
export const gridPad = style({ padding: vars.space['4'] });

export const grid = style({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
  gap: vars.space['3'],
});

export const card = style({
  position: 'relative',
  borderRadius: vars.radius.tile,
  overflow: 'hidden',
  border: `1px solid ${vars.color.hair}`,
  background: vars.color.panel,
  cursor: 'pointer',
  padding: 0,
  textAlign: 'left',
  transition: `border-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { borderColor: vars.color.line2 },
    '&:focus-visible': {
      borderColor: vars.color.accent,
      boxShadow: vars.shadow.focus,
      outline: 'none',
    },
  },
});

export const poster = style({
  width: '100%',
  aspectRatio: '16 / 9',
  objectFit: 'cover',
  display: 'block',
  background: vars.color.sunken,
});

export const posterEmpty = style([
  poster,
  {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: vars.color.fore4,
  },
]);

export const durationBadge = style({
  position: 'absolute',
  right: vars.space['2'],
  top: vars.space['2'],
  padding: `${vars.space['0.5']} ${vars.space['2']}`,
  borderRadius: vars.radius.button,
  background: vars.scrim.strong,
  color: vars.color.fore,
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  fontVariantNumeric: 'tabular-nums',
});

export const cardMeta = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: vars.space['2'],
  padding: `${vars.space['2']} ${vars.space['3']}`,
  // meta (13) = the app-wide "primary item label" size (Browse tiles, facet rows).
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
});

export const cardName = style({
  flex: 1,
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  color: vars.color.fore2,
});

// Audio/silent indicator wrapper — carries the programmatic name (role=img +
// aria-label) so the state isn't conveyed by glyph shape alone.
export const audioIcon = style({
  display: 'inline-flex',
  alignItems: 'center',
  flexShrink: 0,
  color: vars.color.fore3,
});

// Inline code in copy (empty-state path). Styled so it stays in the single UI
// font instead of falling back to the browser monospace default.
export const codeInline = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  backgroundColor: vars.color.surface,
  borderRadius: vars.radius.small,
  padding: '0 4px',
});

/* ---- Player modal ---- */

export const overlay = style({
  position: 'fixed',
  inset: 0,
  backgroundColor: vars.scrim.strong,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 100,
  padding: vars.space['5'],
});

export const playerDialog = style({
  width: 'min(960px, 94vw)',
  background: vars.color.panel,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.panel,
  boxShadow: vars.shadow.pop,
  overflow: 'hidden',
  display: 'flex',
  flexDirection: 'column',
});

export const video = style({
  width: '100%',
  maxHeight: '70vh',
  background: vars.color.void,
  display: 'block',
});

export const playerBar = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  padding: vars.space['3'],
  borderTop: `1px solid ${vars.color.hair}`,
});

export const sceneChips = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space['2'],
  flex: 1,
  minWidth: 0,
});

export const sceneChip = style({
  padding: `${vars.space['0.5']} ${vars.space['2']}`,
  borderRadius: vars.radius.pill,
  border: `1px solid ${vars.color.line}`,
  background: vars.color.panel2,
  color: vars.color.fore3,
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  fontVariantNumeric: 'tabular-nums',
  cursor: 'pointer',
  transition: `border-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: { '&:hover': { borderColor: vars.color.accent2, color: vars.color.fore } },
});

export const closeBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1.5'],
  padding: `${vars.space['1']} ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line}`,
  background: vars.color.surface,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: { '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore } },
});

/* ---- header sort control (Wave 2a) ---- */

export const sortWrap = style({
  position: 'relative',
  display: 'inline-flex',
  alignItems: 'center',
});

export const sortSelect = style({
  appearance: 'none',
  WebkitAppearance: 'none',
  MozAppearance: 'none',
  height: vars.size.controlMd,
  padding: `0 ${vars.space['5']} 0 ${vars.space['3']}`,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  cursor: 'pointer',
  outline: 'none',
  transition: `border-color ${vars.motion.durFast} ${vars.motion.easeOut}, background-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, borderColor: vars.color.accent2 },
  },
});

export const sortCaret = style({
  position: 'absolute',
  right: vars.space['2'],
  top: '50%',
  transform: 'translateY(-50%)',
  color: vars.color.fore3,
  pointerEvents: 'none',
});
