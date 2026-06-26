import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* Settings → label-set manager (Wave 2b). Layout + neutral chrome only; label
   value colors are DATA, applied inline. */

export const wrap = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['3'],
});

export const list = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const setRow = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['3'],
  padding: vars.space['3'],
  borderRadius: vars.radius.panel,
  border: `1px solid ${vars.color.hair}`,
  background: vars.color.panel,
});

export const setHead = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
});

export const grip = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '24px',
  height: '24px',
  flexShrink: 0,
  color: vars.color.fore4,
  cursor: 'grab',
  borderRadius: vars.radius.small,
  selectors: { '&:active': { cursor: 'grabbing' } },
});

export const nameInput = style({
  flex: 1,
  minWidth: 0,
  height: vars.size.controlSm,
  padding: `0 ${vars.space['2']}`,
  background: vars.color.sunken,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore,
  fontSize: vars.fontSize.body,
});

export const iconBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '28px',
  height: vars.size.controlSm,
  flexShrink: 0,
  background: vars.color.surface,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore2,
  cursor: 'pointer',
  selectors: {
    '&:hover': { background: vars.color.hover },
    '&:disabled': { cursor: 'default', color: vars.color.disabledFore },
  },
});

export const toggle = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1'],
  height: vars.size.controlSm,
  padding: `0 ${vars.space['3']}`,
  background: vars.color.surface,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
  cursor: 'pointer',
});

export const toggleOn = style({
  background: vars.color.accentWeak,
  borderColor: vars.color.accent2,
  color: vars.color.fore,
});

export const systemBadge = style({
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  textTransform: 'uppercase',
  letterSpacing: vars.letterSpacing.label,
});

export const valueWrap = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space['2'],
  alignItems: 'center',
});

export const valueChip = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1'],
  height: vars.size.controlXs,
  padding: `0 ${vars.space['2']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line2}`,
  background: vars.color.surface,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
});

export const valueDot = style({
  display: 'inline-block',
  width: '8px',
  height: '8px',
  borderRadius: vars.radius.pill,
  border: `1px solid ${vars.color.line2}`,
  flexShrink: 0,
});

export const removeBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  background: 'transparent',
  border: 'none',
  color: vars.color.fore4,
  cursor: 'pointer',
  padding: 0,
  selectors: { '&:hover': { color: vars.color.fore2 } },
});

export const addRow = style({
  display: 'flex',
  gap: vars.space['2'],
  alignItems: 'center',
});

export const addInput = style({
  flex: 1,
  minWidth: 0,
  height: vars.size.controlSm,
  padding: `0 ${vars.space['2']}`,
  background: vars.color.sunken,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore,
  fontSize: vars.fontSize.meta,
});

export const colorInput = style({
  width: '28px',
  height: vars.size.controlSm,
  padding: 0,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  background: vars.color.sunken,
  cursor: 'pointer',
});

export const newSetRow = style({
  display: 'flex',
  gap: vars.space['2'],
  alignItems: 'center',
  paddingTop: vars.space['2'],
});

export const primaryBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1'],
  height: vars.size.controlSm,
  padding: `0 ${vars.space['3']}`,
  background: vars.color.accent,
  border: `1px solid ${vars.color.accent}`,
  borderRadius: vars.radius.button,
  color: vars.color.onAccent,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  cursor: 'pointer',
  selectors: {
    '&:disabled': {
      cursor: 'default',
      background: vars.color.disabledBg,
      borderColor: vars.color.disabledBg,
      color: vars.color.disabledFore,
    },
  },
});

export const hint = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore4,
});
