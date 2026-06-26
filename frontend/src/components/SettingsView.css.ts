import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   Settings page shell — shared app chrome (command bar + nav)
   over a centered single-column content well. Hosts stacked
   sections: License (Spec J), Keyboard shortcuts, About.
   ============================================================ */

export const scroll = style({
  flex: 1,
  minHeight: 0,
  overflowY: 'auto',
  background: vars.color.void,
});

export const inner = style({
  maxWidth: '760px',
  margin: '0 auto',
  padding: vars.space['6'],
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['6'],
});

/* ---- Section scaffolding (header + panel) ---- */

export const section = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['3'],
});

export const sectionHead = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['1'],
});

export const sectionTitle = style({
  fontSize: vars.fontSize.display,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore,
  letterSpacing: vars.letterSpacing.tight,
});

export const sectionLead = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  lineHeight: vars.lineHeight.base,
});

export const panel = style({
  background: vars.color.panel,
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.panel,
  padding: vars.space['4'],
});

/* ---- Keyboard shortcuts ---- */

export const shortcutGroup = style({
  display: 'flex',
  flexDirection: 'column',
});

export const groupLabel = style({
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.semi,
  letterSpacing: vars.letterSpacing.label,
  textTransform: 'uppercase',
  color: vars.color.fore3,
  marginBottom: vars.space['1'],
  selectors: {
    // Breathing room above a second group within the same panel.
    '&:not(:first-child)': { marginTop: vars.space['4'] },
  },
});

export const shortcutRow = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: vars.space['3'],
  minHeight: vars.size.rowH,
  selectors: {
    '&:not(:last-child)': { borderBottom: `1px solid ${vars.color.hair}` },
  },
});

export const shortcutLabel = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore2,
});

export const keys = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1'],
  flexShrink: 0,
});

/* ---- About ---- */

export const aboutGrid = style({
  display: 'grid',
  gridTemplateColumns: 'auto 1fr',
  gap: `${vars.space['3']} ${vars.space['5']}`,
  alignItems: 'baseline',
});

export const aboutKey = style({
  fontSize: vars.fontSize.label,
  textTransform: 'uppercase',
  letterSpacing: vars.letterSpacing.label,
  color: vars.color.fore3,
});

export const aboutVal = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore,
  lineHeight: vars.lineHeight.base,
});

export const aboutLink = style({
  color: vars.color.accent,
  textDecoration: 'none',
  selectors: { '&:hover': { textDecoration: 'underline' } },
});

/* ---- Appearance: theme switcher (Wave 2a) + accent picker (Wave 4) ---- */

export const appearanceGroup = style({
  display: 'flex',
  flexDirection: 'column',
  selectors: {
    // Breathing room above a second group within the same panel.
    '&:not(:first-child)': { marginTop: vars.space['4'] },
  },
});

export const themeSwitch = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space['2'],
  marginTop: vars.space['1'],
});

export const themeOption = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['2'],
  padding: `${vars.space['2']} ${vars.space['4']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line}`,
  background: vars.color.surface,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, border-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore },
  },
});

export const themeOptionActive = style({
  borderColor: vars.color.accent,
  background: vars.color.accentWeak,
  color: vars.color.fore,
});

/* Accent picker — pre-vetted preset swatches plus a freeform custom color.
   The fill comes from a per-control `--swatch` CSS var (mode-resolved hex). */

export const accentRow = style({
  display: 'flex',
  flexWrap: 'wrap',
  alignItems: 'center',
  gap: vars.space['2'],
  marginTop: vars.space['1'],
});

export const accentSwitch = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space['2'],
});

export const accentSwatch = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '32px',
  height: '32px',
  padding: 0,
  borderRadius: vars.radius.pill,
  border: `2px solid ${vars.color.line}`,
  background: 'var(--swatch)',
  cursor: 'pointer',
  transition: `border-color ${vars.motion.durFast} ${vars.motion.easeOut}, box-shadow ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { borderColor: vars.color.line2 },
  },
});

export const accentSwatchActive = style({
  borderColor: vars.color.fore,
  borderStyle: 'solid',
  // A soft halo so the selected swatch reads as committed without recoloring.
  boxShadow: `0 0 0 2px ${vars.color.panel}, 0 0 0 4px var(--swatch)`,
});

export const accentCheck = style({
  // Ink is computed per-swatch (accentInk → dark or light, whichever has higher
  // contrast on that hue) and passed as `--tick`, so the tick stays legible on
  // both the bright dark-mode swatches and the deeper light-mode ones.
  color: 'var(--tick)',
});

/* Custom accent — a freeform color via the native <input type="color">, hidden
   behind a swatch-shaped label. A dashed border in the empty state reads as
   "add your own"; once chosen it adopts the active swatch treatment. */

export const customSwatch = style({
  position: 'relative',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '32px',
  height: '32px',
  borderRadius: vars.radius.pill,
  border: `2px dashed ${vars.color.line2}`,
  background: 'var(--swatch)',
  color: vars.color.fore3,
  cursor: 'pointer',
  transition: `border-color ${vars.motion.durFast} ${vars.motion.easeOut}, box-shadow ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { borderColor: vars.color.fore3, color: vars.color.fore2 },
    // Native input focus is invisible (opacity 0); surface a ring on the label.
    '&:focus-within': { borderColor: vars.color.accent, boxShadow: vars.shadow.focus },
  },
});

export const customInput = style({
  position: 'absolute',
  inset: 0,
  width: '100%',
  height: '100%',
  margin: 0,
  padding: 0,
  border: 0,
  opacity: 0,
  cursor: 'pointer',
});
