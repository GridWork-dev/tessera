import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   Events — page chrome (command bar, gridRegion, empty/loading
   states) is the SHARED workspace vocabulary (workspace.css).
   This file owns the Events-specific surfaces: the auto-album
   card grid + the event-detail modal (member thumbnails).
   ============================================================ */

export const pad = style({ padding: vars.space['4'] });

export const grid = style({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
  gap: vars.space['3'],
});

export const card = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
  padding: vars.space['4'],
  borderRadius: vars.radius.tile,
  border: `1px solid ${vars.color.hair}`,
  background: vars.color.panel,
  cursor: 'pointer',
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

export const cardLabel = style({
  fontSize: vars.fontSize.heading,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const cardRange = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore2,
  fontVariantNumeric: 'tabular-nums',
});

export const cardFoot = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: vars.space['2'],
  marginTop: vars.space['1'],
});

export const cardMembers = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore3,
  fontVariantNumeric: 'tabular-nums',
});

export const cardCentroid = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  fontVariantNumeric: 'tabular-nums',
});

// Inline code in copy (empty-state hints).
export const codeInline = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  backgroundColor: vars.color.surface,
  borderRadius: vars.radius.small,
  padding: '0 4px',
});

/* ---- Event detail modal ---- */

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

export const dialog = style({
  width: 'min(900px, 94vw)',
  maxHeight: '88vh',
  background: vars.color.panel,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.panel,
  boxShadow: vars.shadow.pop,
  overflow: 'hidden',
  display: 'flex',
  flexDirection: 'column',
});

export const dialogHead = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: vars.space['3'],
  padding: vars.space['4'],
  borderBottom: `1px solid ${vars.color.hair}`,
});

export const dialogText = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['0.5'],
  minWidth: 0,
});

export const dialogTitle = style({
  fontSize: vars.fontSize.display,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore,
  letterSpacing: vars.letterSpacing.tight,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const dialogMeta = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  fontVariantNumeric: 'tabular-nums',
});

export const dialogBody = style({
  overflowY: 'auto',
  padding: vars.space['4'],
});

export const modalState = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: vars.space['6'],
  color: vars.color.fore3,
  fontSize: vars.fontSize.meta,
});

export const thumbGrid = style({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))',
  gap: vars.space['2'],
});

export const thumb = style({
  width: '100%',
  aspectRatio: '1 / 1',
  objectFit: 'cover',
  display: 'block',
  borderRadius: vars.radius.tile,
  border: `1px solid ${vars.color.hair}`,
  background: vars.color.sunken,
});

export const closeBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1.5'],
  flexShrink: 0,
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
