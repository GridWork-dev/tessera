import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* Top-level crash fallback (ErrorBoundary). Calm, centered, on-brand — NOT a
   stack-trace dump. The error text is shown in a quiet collapsible block because
   the packaged Tauri app has no dev overlay to explain a white screen. */

export const wrap = style({
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space['4'],
  minHeight: '100vh',
  padding: vars.space['6'],
  textAlign: 'center',
  backgroundColor: vars.color.void,
  color: vars.color.fore,
});

export const icon = style({ color: vars.color.sugg });

export const title = style({
  fontSize: vars.fontSize.display,
  fontWeight: vars.fontWeight.semi,
  letterSpacing: vars.letterSpacing.tight,
  color: vars.color.fore,
});

export const message = style({
  fontSize: vars.fontSize.body,
  color: vars.color.fore2,
  maxWidth: '52ch',
  lineHeight: vars.lineHeight.base,
});

export const actions = style({
  display: 'flex',
  gap: vars.space['3'],
  flexWrap: 'wrap',
  justifyContent: 'center',
  marginTop: vars.space['2'],
});

export const reloadBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['2'],
  height: vars.size.controlLg,
  padding: `0 ${vars.space['4']}`,
  backgroundColor: vars.color.accent,
  color: vars.color.onAccent,
  border: 'none',
  borderRadius: vars.radius.button,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.heading,
  fontWeight: vars.fontWeight.semi,
  cursor: 'pointer',
  transition: `filter ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { filter: 'brightness(1.06)' },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});

export const details = style({
  marginTop: vars.space['2'],
  maxWidth: 'min(680px, 90vw)',
  textAlign: 'left',
});

export const summary = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  cursor: 'pointer',
  userSelect: 'none',
});

export const trace = style({
  marginTop: vars.space['2'],
  padding: vars.space['3'],
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore3,
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  lineHeight: vars.lineHeight.snug,
  whiteSpace: 'pre-wrap',
  overflowWrap: 'anywhere',
  maxHeight: '40vh',
  overflowY: 'auto',
});
