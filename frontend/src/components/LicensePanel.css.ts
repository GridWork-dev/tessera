import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   License panel (Spec J / PART 5). A single calm card: current
   entitlement, what Pro unlocks (honest — no content is ever
   gated), a soft dismissible upgrade note, and a local activate
   / remove flow. Verification is OFFLINE. Pigment tokens
   only — no gradient/glow (impeccable).
   ============================================================ */

export const card = style({
  width: '100%',
  maxWidth: '620px',
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['5'],
  padding: vars.space['6'],
  background: vars.color.panel,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.panel,
});

export const header = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
});

export const glyph = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '34px',
  height: '34px',
  flexShrink: 0,
  borderRadius: vars.radius.button,
  background: vars.color.surface,
  border: `1px solid ${vars.color.line2}`,
  color: vars.color.fore2,
});

export const headerText = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['0.5'],
});

export const title = style({
  margin: 0,
  fontSize: vars.fontSize.heading,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore,
});

export const subtitle = style({
  margin: 0,
  color: vars.color.fore3,
  fontSize: vars.fontSize.meta,
  lineHeight: vars.lineHeight.snug,
});

/* ---- current status ---- */

export const statusRow = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  padding: `${vars.space['3']} ${vars.space['4']}`,
  background: vars.color.sunken,
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.button,
});

export const statusLabel = style({
  fontSize: vars.fontSize.label,
  textTransform: 'uppercase',
  letterSpacing: vars.letterSpacing.label,
  color: vars.color.fore3,
});

export const statusValue = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1.5'],
  marginLeft: 'auto',
  fontSize: vars.fontSize.heading,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore2,
});

export const statusValuePro = style({ color: vars.color.accent });

/* ---- feature list ---- */

export const featureList = style({
  display: 'flex',
  flexDirection: 'column',
  gap: '1px',
  borderRadius: vars.radius.button,
  overflow: 'hidden',
  border: `1px solid ${vars.color.hair}`,
});

export const featureRow = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  padding: `${vars.space['3']} ${vars.space['3']}`,
  background: vars.color.panel2,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore2,
});

export const featureIconOn = style({ color: vars.color.accent, flexShrink: 0 });
export const featureIconOff = style({ color: vars.color.fore4, flexShrink: 0 });

export const featureName = style({ flex: 1 });

export const featureState = style({
  fontSize: vars.fontSize.micro,
  textTransform: 'uppercase',
  letterSpacing: vars.letterSpacing.label,
  color: vars.color.fore4,
});

export const freeNote = style({
  margin: 0,
  color: vars.color.fore4,
  fontSize: vars.fontSize.micro,
  lineHeight: vars.lineHeight.snug,
});

/* ---- soft, dismissible upgrade note ---- */

export const upgradeNote = style({
  display: 'flex',
  alignItems: 'flex-start',
  gap: vars.space['2'],
  padding: `${vars.space['3']} ${vars.space['3']}`,
  background: vars.color.accentWeak,
  border: `1px solid ${vars.color.accent2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
  lineHeight: vars.lineHeight.snug,
});

export const upgradeIcon = style({ color: vars.color.accent, flexShrink: 0, marginTop: '1px' });
export const upgradeText = style({ flex: 1 });

export const upgradePrice = style({ color: vars.color.accent, fontWeight: vars.fontWeight.semi });

export const dismiss = style({
  flexShrink: 0,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '20px',
  height: '20px',
  padding: 0,
  background: 'none',
  border: 'none',
  borderRadius: vars.radius.button,
  color: vars.color.fore3,
  cursor: 'pointer',
  selectors: {
    '&:hover': { color: vars.color.fore, background: vars.color.hover },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});

/* ---- activate (paste / drop a token) ---- */

export const field = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const label = style({
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.med,
  color: vars.color.fore2,
  textTransform: 'uppercase',
  letterSpacing: vars.letterSpacing.label,
});

export const textarea = style({
  width: '100%',
  minHeight: '76px',
  resize: 'vertical',
  padding: vars.space['3'],
  background: vars.color.sunken,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore,
  fontSize: vars.fontSize.meta,
  fontFamily: vars.font.mono,
  lineHeight: vars.lineHeight.snug,
  outline: 'none',
  overflowWrap: 'anywhere',
  selectors: {
    '&::placeholder': { color: vars.color.fore4 },
    '&:focus': { borderColor: vars.color.accent2, boxShadow: vars.shadow.focus },
  },
});

export const dropActive = style({
  borderColor: vars.color.accent,
  background: vars.color.accentWeak,
});

export const dropHint = style({
  margin: 0,
  color: vars.color.fore4,
  fontSize: vars.fontSize.micro,
});

/* ---- actions ---- */

export const actions = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
});

export const spacer = style({ flex: 1 });

export const button = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1.5'],
  height: vars.size.controlLg,
  padding: `0 ${vars.space['4']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line2}`,
  background: vars.color.surface,
  color: vars.color.fore,
  fontSize: vars.fontSize.heading,
  fontWeight: vars.fontWeight.med,
  fontFamily: vars.font.sans,
  cursor: 'pointer',
  transition: `background ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': { background: vars.color.hover },
    '&:disabled': {
      background: vars.color.disabledBg,
      color: vars.color.disabledFore,
      cursor: 'not-allowed',
      borderColor: vars.color.hair,
    },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});

export const buttonPrimary = style({
  background: vars.color.accent,
  borderColor: vars.color.accent,
  color: vars.color.onAccent,
  fontWeight: vars.fontWeight.semi,
  selectors: {
    '&:hover:not(:disabled)': { background: vars.color.accent2 },
  },
});

export const buttonDanger = style({
  color: vars.color.nsfw,
  selectors: {
    '&:hover:not(:disabled)': { background: vars.color.negBg, borderColor: vars.color.negLine },
  },
});

/* ---- inline status messages ---- */

export const ok = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  margin: 0,
  padding: `${vars.space['2']} ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  background: vars.color.accentWeak,
  border: `1px solid ${vars.color.accent2}`,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
});

export const error = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  margin: 0,
  padding: `${vars.space['2']} ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  background: vars.color.negBg,
  border: `1px solid ${vars.color.negLine}`,
  color: vars.color.nsfw,
  fontSize: vars.fontSize.meta,
});

export const loading = style({
  color: vars.color.fore3,
  fontSize: vars.fontSize.meta,
});
