import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

export const overlay = style({
  position: 'fixed',
  inset: 0,
  backgroundColor: vars.scrim.soft,
  backdropFilter: 'blur(2px)',
  zIndex: 100,
});

export const dialog = style({
  position: 'fixed',
  top: '18vh',
  left: '50%',
  transform: 'translateX(-50%)',
  width: 'min(560px, 92vw)',
  maxHeight: '64vh',
  display: 'flex',
  flexDirection: 'column',
  backgroundColor: vars.color.panel,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.panel,
  boxShadow: vars.shadow.pop,
  overflow: 'hidden',
  zIndex: 101,
});

export const input = style({
  appearance: 'none',
  border: 'none',
  outline: 'none',
  background: 'transparent',
  color: vars.color.fore,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.body,
  padding: `${vars.space[4]} ${vars.space[5]}`,
  borderBottom: `1px solid ${vars.color.hair}`,
  width: '100%',
  '::placeholder': { color: vars.color.fore4 },
});

export const list = style({
  overflowY: 'auto',
  padding: vars.space[2],
});

export const empty = style({
  padding: `${vars.space[5]} ${vars.space[4]}`,
  textAlign: 'center',
  color: vars.color.fore4,
  fontSize: vars.fontSize.meta,
});

export const group = style({ marginBottom: vars.space[2] });

// cmdk renders the heading inside [cmdk-group-heading]; style it globally.
globalStyle(`${group} [cmdk-group-heading]`, {
  padding: `${vars.space[2]} ${vars.space[3]}`,
  fontSize: vars.fontSize.micro,
  textTransform: 'uppercase',
  letterSpacing: vars.letterSpacing.label,
  color: vars.color.fore4,
});

export const item = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space[3],
  padding: `${vars.space[2]} ${vars.space[3]}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
  cursor: 'pointer',
  userSelect: 'none',
  selectors: {
    '&[aria-selected="true"]': {
      backgroundColor: vars.color.hover,
      color: vars.color.fore,
    },
  },
});

export const itemLabel = style({ flex: 1, minWidth: 0 });

export const itemMeta = style({
  color: vars.color.fore4,
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
});
