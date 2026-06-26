import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   First-run setup wizard (Spec F). A centered, single-column
   card flow over the void: a step rail, one active step panel,
   and a footer with Back/Next. Pigment tokens only — no
   gradients/glow (impeccable). Self-contained surface; it owns
   the full viewport and is mounted by the /setup route.
   ============================================================ */

export const screen = style({
  minHeight: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: vars.space['6'],
  background: vars.color.void,
  overflowY: 'auto',
});

export const card = style({
  width: '100%',
  maxWidth: '640px',
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['5'],
  padding: vars.space['6'],
  background: vars.color.panel,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.panel,
  boxShadow: vars.shadow.pop,
});

export const header = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const brand = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  color: vars.color.fore,
  fontSize: vars.fontSize.brand,
  fontWeight: vars.fontWeight.bold,
  letterSpacing: vars.letterSpacing.tight,
});

export const brandGlyph = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '22px',
  height: '22px',
  flexShrink: 0,
  // The BrandFacet tile is jade via currentColor; no chip background.
  color: vars.color.accent,
});

export const subtitle = style({
  margin: 0,
  color: vars.color.fore3,
  fontSize: vars.fontSize.meta,
  lineHeight: vars.lineHeight.snug,
});

/* ---- step rail ---- */

export const rail = style({
  display: 'flex',
  gap: vars.space['2'],
  listStyle: 'none',
  margin: 0,
  padding: 0,
});

export const railStep = style({
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['1'],
});

export const railBar = style({
  height: '3px',
  borderRadius: vars.radius.pill,
  background: vars.color.surface,
});

export const railBarActive = style({ background: vars.color.accent });
export const railBarDone = style({ background: vars.color.accent2 });

export const railLabel = style({
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  textTransform: 'uppercase',
  letterSpacing: vars.letterSpacing.label,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
});

export const railLabelActive = style({ color: vars.color.fore2 });

/* ---- step body ---- */

export const step = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['4'],
  minHeight: '220px',
});

export const stepCount = style({
  margin: 0,
  color: vars.color.fore4,
  fontSize: vars.fontSize.micro,
  textTransform: 'uppercase',
  letterSpacing: vars.letterSpacing.label,
  fontVariantNumeric: 'tabular-nums',
});

export const stepTitle = style({
  margin: 0,
  fontSize: vars.fontSize.display,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore,
  // Focus target on advance (tabIndex=-1); suppress the default outline since
  // the step-count label + heading text already signal arrival.
  outline: 'none',
});

export const stepHint = style({
  margin: 0,
  color: vars.color.fore3,
  fontSize: vars.fontSize.meta,
  lineHeight: vars.lineHeight.snug,
});

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

export const input = style({
  width: '100%',
  height: '42px',
  padding: `0 ${vars.space['3']}`,
  background: vars.color.sunken,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore,
  fontSize: vars.fontSize.body,
  fontFamily: vars.font.sans,
  outline: 'none',
  selectors: {
    '&::placeholder': { color: vars.color.fore4 },
    '&:focus': { borderColor: vars.color.accent2, boxShadow: vars.shadow.focus },
  },
});

/* ---- option list (compute backends) ---- */

export const options = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const option = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  padding: `${vars.space['3']} ${vars.space['3']}`,
  background: vars.color.panel2,
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore2,
  fontSize: vars.fontSize.heading,
  textAlign: 'left',
  cursor: 'pointer',
  transition: `border-color ${vars.motion.durFast} ${vars.motion.easeOut}, background ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { background: vars.color.hover },
  },
});

export const optionActive = style({
  borderColor: vars.color.accent,
  background: vars.color.accentWeak,
  color: vars.color.fore,
});

export const optionMeta = style({
  marginLeft: 'auto',
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  fontVariantNumeric: 'tabular-nums',
});

export const badge = style({
  padding: `1px ${vars.space['2']}`,
  borderRadius: vars.radius.pill,
  background: vars.color.accentWeak,
  border: `1px solid ${vars.color.accent2}`,
  color: vars.color.accent,
  fontSize: vars.fontSize.micro,
  fontWeight: vars.fontWeight.med,
});

/* ---- weights manifest preview ---- */

export const previewList = style({
  display: 'flex',
  flexDirection: 'column',
  gap: '1px',
  borderRadius: vars.radius.button,
  overflow: 'hidden',
  border: `1px solid ${vars.color.hair}`,
});

export const previewRow = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  padding: `${vars.space['2']} ${vars.space['3']}`,
  background: vars.color.panel2,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore2,
});

export const previewSize = style({
  marginLeft: 'auto',
  fontVariantNumeric: 'tabular-nums',
  color: vars.color.fore3,
});

export const totalRow = style({
  display: 'flex',
  alignItems: 'baseline',
  gap: vars.space['2'],
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
});

export const totalValue = style({
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore,
  fontVariantNumeric: 'tabular-nums',
});

/* ---- AGPL / auth toggles ---- */

export const checkRow = style({
  display: 'flex',
  alignItems: 'flex-start',
  gap: vars.space['2'],
  padding: vars.space['3'],
  background: vars.color.panel2,
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.button,
  cursor: 'pointer',
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
  lineHeight: vars.lineHeight.snug,
});

export const checkBox = style({
  marginTop: '2px',
  accentColor: vars.color.accent,
  width: '16px',
  height: '16px',
  flexShrink: 0,
});

export const checkNote = style({
  display: 'block',
  marginTop: '2px',
  color: vars.color.fore4,
  fontSize: vars.fontSize.micro,
});

/* ---- inline status / errors ---- */

export const note = style({
  margin: 0,
  padding: `${vars.space['2']} ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  background: vars.color.accentWeak,
  border: `1px solid ${vars.color.accent2}`,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
  lineHeight: vars.lineHeight.snug,
});

export const error = style({
  margin: 0,
  padding: `${vars.space['2']} ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  background: vars.color.negBg,
  border: `1px solid ${vars.color.negLine}`,
  color: vars.color.nsfw,
  fontSize: vars.fontSize.meta,
});

/* ---- footer / actions ---- */

export const footer = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  paddingTop: vars.space['3'],
  borderTop: `1px solid ${vars.color.hair}`,
});

export const footerSpacer = style({ flex: 1 });

export const button = style({
  height: '40px',
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
