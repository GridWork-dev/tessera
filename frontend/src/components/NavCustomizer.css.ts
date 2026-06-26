import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* Settings → nav/dashboard customizer (Wave 2b). Layout + neutral chrome. */

export const list = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const row = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  padding: `${vars.space['2']} ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.hair}`,
  background: vars.color.panel,
});

export const rowGated = style({
  background: vars.color.disabledBg,
  color: vars.color.disabledFore,
});

export const grip = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '22px',
  height: '22px',
  flexShrink: 0,
  color: vars.color.fore4,
  cursor: 'grab',
  borderRadius: vars.radius.small,
  selectors: { '&:active': { cursor: 'grabbing' } },
});

export const gripDisabled = style({
  color: vars.color.disabledFore,
  cursor: 'not-allowed',
});

export const icon = style({
  display: 'inline-flex',
  alignItems: 'center',
  color: vars.color.fore3,
  flexShrink: 0,
});

export const label = style({
  flex: 1,
  minWidth: 0,
  fontSize: vars.fontSize.body,
  color: vars.color.fore,
});

export const unavailable = style({
  fontSize: vars.fontSize.micro,
  textTransform: 'uppercase',
  letterSpacing: vars.letterSpacing.label,
  color: vars.color.fore4,
});

export const toggle = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1'],
  height: '26px',
  padding: `0 ${vars.space['3']}`,
  background: vars.color.surface,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
  cursor: 'pointer',
  selectors: {
    '&:disabled': {
      cursor: 'not-allowed',
      background: vars.color.disabledBg,
      color: vars.color.disabledFore,
      borderColor: vars.color.disabledBg,
    },
  },
});

export const toggleHidden = style({
  background: 'transparent',
  color: vars.color.fore4,
});
