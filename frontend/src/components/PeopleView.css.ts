import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   People (faces) — page chrome (command bar, body, empty/loading
   states) is the SHARED workspace vocabulary (workspace.css),
   identical to Browse/Videos. This file owns only the people-
   specific surfaces: the cluster grid, the person detail panel,
   the face crop tiles, and the privacy opt-in / action affordances.
   ============================================================ */

export const gridPad = style({ padding: vars.space['4'] });

export const grid = style({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
  gap: vars.space['3'],
});

/* ---- person card ---- */

export const card = style({
  position: 'relative',
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
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

export const cardActive = style({
  borderColor: vars.color.accent,
  boxShadow: vars.shadow.focus,
});

export const cover = style({
  width: '100%',
  aspectRatio: '1 / 1',
  objectFit: 'cover',
  display: 'block',
  background: vars.color.sunken,
});

export const coverEmpty = style([
  cover,
  {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: vars.color.fore4,
  },
]);

export const cardMeta = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: vars.space['2'],
  padding: `0 ${vars.space['3']} ${vars.space['3']}`,
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

export const cardNameUnnamed = style([cardName, { color: vars.color.fore3, fontStyle: 'italic' }]);

export const cardCount = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  fontVariantNumeric: 'tabular-nums',
});

export const codeInline = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  backgroundColor: vars.color.surface,
  borderRadius: vars.radius.small,
  padding: '0 4px',
});

/* ---- rail: clustering / purge actions ---- */

export const railActions = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
  padding: vars.space['4'],
});

/* ---- buttons ---- */

const buttonBase = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space['1.5'],
  padding: `${vars.space['1']} ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line}`,
  background: vars.color.surface,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, border-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:disabled': {
      background: vars.color.disabledBg,
      color: vars.color.disabledFore,
      cursor: 'not-allowed',
    },
  },
} as const;

export const button = style(buttonBase);

export const buttonAccent = style([
  buttonBase,
  {
    background: vars.color.accent,
    borderColor: vars.color.accent,
    color: vars.color.onAccent,
    selectors: {
      '&:hover:not(:disabled)': { background: vars.color.accent2, color: vars.color.onAccent },
    },
  },
]);

export const buttonDanger = style([
  buttonBase,
  {
    background: vars.color.negBg,
    borderColor: vars.color.negLine,
    color: vars.color.nsfw,
    selectors: {
      '&:hover:not(:disabled)': { borderColor: vars.color.nsfw, color: vars.color.nsfw },
    },
  },
]);

/* ---- detail panel (overlay drawer) ---- */

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
  width: 'min(880px, 94vw)',
  maxHeight: '90vh',
  background: vars.color.panel,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.panel,
  boxShadow: vars.shadow.pop,
  overflow: 'hidden',
  display: 'flex',
  flexDirection: 'column',
});

export const dialogHeader = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  padding: vars.space['4'],
  borderBottom: `1px solid ${vars.color.hair}`,
});

export const dialogTitle = style({
  flex: 1,
  minWidth: 0,
  fontSize: vars.fontSize.heading,
  fontWeight: vars.fontWeight.med,
  color: vars.color.fore,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const dialogBody = style({
  overflowY: 'auto',
  padding: vars.space['4'],
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['4'],
});

export const dialogActions = style({
  display: 'flex',
  flexWrap: 'wrap',
  alignItems: 'center',
  gap: vars.space['2'],
});

export const sectionLabel = style({
  fontSize: vars.fontSize.label,
  letterSpacing: vars.letterSpacing.label,
  textTransform: 'uppercase',
  color: vars.color.fore3,
});

/* ---- inline name editor + merge picker ---- */

export const input = style({
  height: vars.size.controlMd,
  padding: `0 ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line2}`,
  background: vars.color.sunken,
  color: vars.color.fore,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  selectors: {
    '&:focus': { borderColor: vars.color.accent, outline: 'none', boxShadow: vars.shadow.focus },
  },
});

export const select = style([input, { paddingRight: vars.space['2'] }]);

export const inlineRow = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  flexWrap: 'wrap',
});

/* ---- face crop grid (inside detail) ---- */

export const faceGrid = style({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(96px, 1fr))',
  gap: vars.space['2'],
});

export const faceTile = style({
  position: 'relative',
  borderRadius: vars.radius.tile,
  overflow: 'hidden',
  border: `1px solid ${vars.color.hair}`,
  background: vars.color.sunken,
});

export const faceImg = style({
  width: '100%',
  aspectRatio: '1 / 1',
  objectFit: 'cover',
  display: 'block',
  background: vars.color.sunken,
});

export const faceImgEmpty = style([
  faceImg,
  {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: vars.color.fore4,
  },
]);

export const faceSplitBtn = style({
  position: 'absolute',
  right: vars.space['1'],
  top: vars.space['1'],
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '22px',
  height: '22px',
  padding: 0,
  borderRadius: vars.radius.pill,
  border: 'none',
  background: vars.scrim.strong,
  color: vars.color.fore,
  cursor: 'pointer',
  transition: `color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: { '&:hover': { color: vars.color.accent } },
});

/* ---- privacy opt-in empty state (403) ---- */

export const optIn = style({
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space['3'],
  height: '100%',
  padding: vars.space['7'],
  textAlign: 'center',
  color: vars.color.fore3,
});

export const optInIcon = style({ color: vars.color.accent });

export const optInTitle = style({
  fontSize: vars.fontSize.display,
  fontWeight: vars.fontWeight.med,
  color: vars.color.fore,
});

export const optInBody = style({
  fontSize: vars.fontSize.body,
  color: vars.color.fore3,
  maxWidth: '46ch',
  lineHeight: vars.lineHeight.base,
});

export const codeBlock = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore2,
  background: vars.color.sunken,
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.button,
  padding: `${vars.space['2']} ${vars.space['3']}`,
});

/* ---- error banner inside dialog ---- */

export const errorBanner = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.nsfw,
  background: vars.color.negBg,
  border: `1px solid ${vars.color.negLine}`,
  borderRadius: vars.radius.button,
  padding: `${vars.space['2']} ${vars.space['3']}`,
});

/* ---- inline rename affordance on the card (Wave 2a) ---- */

export const cardNameEditable = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
  cursor: 'text',
});

export const cardEditIcon = style({
  opacity: 0,
  flexShrink: 0,
  color: vars.color.fore4,
  transition: `opacity ${vars.motion.durFast} ${vars.motion.easeOut}`,
});

// The pencil hint stays invisible until the card is hovered, so the chrome
// recedes (PRODUCT.md: quiet) yet the affordance stays discoverable. A
// globalStyle is required to target the icon from the card's hover state
// (vanilla-extract can't put another element's class in a `selectors` key).
globalStyle(`${card}:hover ${cardEditIcon}`, { opacity: 1 });

/* ---- button-grid merge picker (replaces the <select>) ---- */

export const mergeSection = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const mergeOptions = style({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
  gap: vars.space['2'],
});

export const mergeOption = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['2'],
  padding: `${vars.space['2']} ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line}`,
  background: vars.color.surface,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  cursor: 'pointer',
  textAlign: 'left',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, border-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': {
      backgroundColor: vars.color.hover,
      borderColor: vars.color.accent2,
      color: vars.color.fore,
    },
    '&:disabled': {
      background: vars.color.disabledBg,
      color: vars.color.disabledFore,
      cursor: 'not-allowed',
    },
  },
});

export const mergeOptionName = style({
  flex: 1,
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const mergeCount = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  fontVariantNumeric: 'tabular-nums',
});
