import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   Active-learning panel — content-only (no app chrome). Two
   stacked sections: the uncertainty queue (keep/reject cards)
   and the few-shot probe (preview count + explicit apply).
   Slots into the existing /training route as a tab/section.
   ============================================================ */

export const wrap = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['5'],
  padding: vars.space['5'],
  overflowY: 'auto',
  height: '100%',
});

export const section = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['4'],
  padding: vars.space['4'],
  background: vars.color.panel,
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.panel,
});

export const sectionHead = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  color: vars.color.fore2,
});

export const sectionTitle = style({
  fontSize: vars.fontSize.heading,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore,
});

export const spacer = style({ flex: 1 });

export const counts = style({
  display: 'flex',
  gap: vars.space['2'],
});

export const countChip = style({
  padding: `${vars.space['0.5']} ${vars.space['2']}`,
  borderRadius: vars.radius.button,
  background: vars.color.surface,
  border: `1px solid ${vars.color.hair}`,
  color: vars.color.fore3,
  fontSize: vars.fontSize.micro,
  fontVariantNumeric: 'tabular-nums',
});

export const coldNote = style({
  margin: 0,
  padding: `${vars.space['2']} ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  background: vars.color.accentWeak,
  border: `1px solid ${vars.color.accent2}`,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
  lineHeight: vars.lineHeight.snug,
});

/* ---- Queue grid ---- */

export const grid = style({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
  gap: vars.space['3'],
});

export const card = style({
  display: 'flex',
  flexDirection: 'column',
  borderRadius: vars.radius.tile,
  overflow: 'hidden',
  border: `1px solid ${vars.color.hair}`,
  background: vars.color.panel2,
  transition: `opacity ${vars.motion.durFast} ${vars.motion.easeOut}`,
});

export const cardPending = style({ opacity: 0.55 });

export const thumbWrap = style({ position: 'relative' });

export const thumb = style({
  width: '100%',
  aspectRatio: '1 / 1',
  objectFit: 'cover',
  display: 'block',
  background: vars.color.sunken,
});

export const thumbEmpty = style([
  thumb,
  {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: vars.color.fore4,
  },
]);

export const scoreBadge = style({
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

export const cardActions = style({
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: '1px',
  background: vars.color.hair,
});

export const labelBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space['1.5'],
  padding: `${vars.space['2']} ${vars.space['2']}`,
  border: 'none',
  background: vars.color.panel2,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': { backgroundColor: vars.color.hover },
    '&:focus-visible': { outline: 'none', boxShadow: vars.shadow.focus },
    '&:disabled': { cursor: 'default' },
  },
});

export const labelBtnOn = style({
  background: vars.color.active,
});

/* ---- Probe form ---- */

export const probeForm = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['4'],
});

export const field = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const fieldLabel = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.med,
  color: vars.color.fore3,
  letterSpacing: vars.letterSpacing.label,
});

export const thresholdValue = style({
  fontFamily: vars.font.mono,
  fontVariantNumeric: 'tabular-nums',
  color: vars.color.fore,
});

export const range = style({
  width: '100%',
  accentColor: vars.color.accent,
});

export const previewBtn = style({
  alignSelf: 'flex-start',
  padding: `${vars.space['2']} ${vars.space['4']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.accent2}`,
  background: vars.color.accentWeak,
  color: vars.color.fore,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': { backgroundColor: vars.color.hover },
    '&:focus-visible': { outline: 'none', boxShadow: vars.shadow.focus },
    '&:disabled': {
      cursor: 'default',
      background: vars.color.disabledBg,
      borderColor: vars.color.hair,
      color: vars.color.disabledFore,
    },
  },
});

export const previewResult = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
  padding: vars.space['4'],
  borderRadius: vars.radius.panel,
  background: vars.color.sunken,
  border: `1px solid ${vars.color.hair}`,
});

export const bigCount = style({
  fontSize: vars.fontSize.display,
  fontWeight: vars.fontWeight.bold,
  fontVariantNumeric: 'tabular-nums',
  color: vars.color.accent,
});

export const bigCountLabel = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
});

export const applyRow = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  marginTop: vars.space['2'],
  flexWrap: 'wrap',
});

export const applyIcon = style({ color: vars.color.fore3, flexShrink: 0 });

export const input = style({
  flex: '1 1 120px',
  minWidth: 0,
  padding: `${vars.space['2']} ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line2}`,
  background: vars.color.void,
  color: vars.color.fore,
  fontSize: vars.fontSize.meta,
  selectors: {
    '&:focus-visible': {
      outline: 'none',
      borderColor: vars.color.accent,
      boxShadow: vars.shadow.focus,
    },
    '&::placeholder': { color: vars.color.fore4 },
  },
});

export const applyBtn = style({
  flexShrink: 0,
  padding: `${vars.space['2']} ${vars.space['4']}`,
  borderRadius: vars.radius.button,
  border: 'none',
  background: vars.color.accent,
  color: vars.color.onAccent,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.semi,
  cursor: 'pointer',
  transition: `opacity ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': { opacity: 0.9 },
    '&:focus-visible': { outline: 'none', boxShadow: vars.shadow.focus },
    '&:disabled': {
      cursor: 'default',
      background: vars.color.disabledBg,
      color: vars.color.disabledFore,
    },
  },
});

export const applyHint = style({
  margin: 0,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  lineHeight: vars.lineHeight.snug,
});

export const errLine = style({
  margin: 0,
  fontSize: vars.fontSize.meta,
  color: vars.color.nsfw,
});

export const okLine = style({
  margin: 0,
  fontSize: vars.fontSize.meta,
  color: vars.color.sfw,
});

/* ---- Shared inline code + empty/error state ---- */

export const code = style({
  fontFamily: vars.font.sans,
  fontSize: 'inherit',
  color: vars.color.fore3,
  backgroundColor: vars.color.surface,
  borderRadius: vars.radius.small,
  padding: '0 4px',
});

export const state = style({
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space['2'],
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
  maxWidth: '40ch',
  lineHeight: vars.lineHeight.base,
});
