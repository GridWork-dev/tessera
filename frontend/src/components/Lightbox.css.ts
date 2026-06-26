import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   Docked lightbox — full-region overlay. Scrim dim + a framed,
   contained image with a pop shadow (NOT glassmorphism). Bottom
   metadata strip + optional neighbor filmstrip.
   ============================================================ */

export const overlay = style({
  position: 'fixed',
  inset: 0,
  zIndex: 100,
  display: 'flex',
  flexDirection: 'column',
  backgroundColor: vars.scrim.strong,
  // Fade the whole overlay in; collapses to instant under reduced-motion (global rule).
  animationName: 'none',
});

// The clickable scrim sits behind the stage; clicking it closes the lightbox.
// It fills the upper region above the metadata strip.
export const stage = style({
  position: 'relative',
  flex: 1,
  minHeight: 0,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: vars.space['6'],
});

export const figure = style({
  position: 'relative',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  maxWidth: '100%',
  maxHeight: '100%',
  margin: 0,
  // Sit above the scrim so clicks on the image don't close.
  zIndex: 1,
  pointerEvents: 'none', // let scrim clicks through the empty box; img re-enables
});

export const image = style({
  display: 'block',
  maxWidth: '100%',
  maxHeight: '100%',
  width: 'auto',
  height: 'auto',
  objectFit: 'contain',
  borderRadius: vars.radius.panel,
  backgroundColor: vars.color.sunken,
  boxShadow: vars.shadow.pop,
  pointerEvents: 'auto',
  userSelect: 'none',
});

export const placeholder = style({
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space['2'],
  width: 'min(60vw, 420px)',
  aspectRatio: '4 / 3',
  borderRadius: vars.radius.panel,
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.line}`,
  color: vars.color.fore3,
  boxShadow: vars.shadow.pop,
  pointerEvents: 'auto',
});

export const placeholderHint = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore4,
});

/* ---- Nav arrows ---- */

const navBase = style({
  position: 'absolute',
  top: '50%',
  transform: 'translateY(-50%)',
  zIndex: 2,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '44px',
  height: '44px',
  color: vars.color.fore,
  backgroundColor: vars.color.panel2,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.pill,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}, border-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': {
      backgroundColor: vars.color.hover,
      borderColor: vars.color.accent2,
    },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
    '&:disabled': {
      color: vars.color.disabledFore,
      backgroundColor: vars.color.disabledBg,
      cursor: 'default',
    },
  },
});

export const navPrev = style([navBase, { left: vars.space['4'] }]);
export const navNext = style([navBase, { right: vars.space['4'] }]);

/* ---- Close button (top-right) ---- */

export const closeBtn = style({
  position: 'absolute',
  top: vars.space['4'],
  right: vars.space['4'],
  zIndex: 2,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '38px',
  height: vars.size.controlLg,
  color: vars.color.fore2,
  backgroundColor: vars.color.panel2,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.pill,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});

/* ---- Bottom metadata strip ---- */

export const strip = style({
  flexShrink: 0,
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['3'],
  padding: `${vars.space['3']} ${vars.space['5']}`,
  backgroundColor: vars.color.panel,
  borderTop: `1px solid ${vars.color.line}`,
});

export const stripRow = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['4'],
  // Wrap on narrow viewports so the filename + flag controls never clip / push
  // off-screen (the strip has no @media of its own; a phone is < the 42ch cap).
  flexWrap: 'wrap',
});

export const stripMeta = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  // Allow the filename child to shrink-and-ellipsis instead of forcing overflow.
  minWidth: 0,
});

export const indexCount = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  fontVariantNumeric: 'tabular-nums',
  whiteSpace: 'nowrap',
});

// Filename caption — mono, secondary, truncates rather than wrapping the strip.
export const filename = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore2,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  minWidth: 0,
  // Viewport-relative cap so a long filename can't exceed a phone's width.
  maxWidth: 'min(42ch, 60vw)',
});

export const stripSpacer = style({ flex: 1 });

export const flagGroup = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['1'],
});

export const flagBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1.5'],
  height: vars.size.controlSm,
  padding: `0 ${vars.space['3']}`,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
    '&:disabled': { color: vars.color.disabledFore, cursor: 'default' },
  },
});

export const flagBtnActive = style({
  backgroundColor: vars.color.accentWeak,
  borderColor: vars.color.accent2,
  color: vars.color.fore,
});

export const flagError = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.nsfw,
});

/* ---- Filmstrip ---- */

export const filmstrip = style({
  display: 'flex',
  gap: vars.space['1'],
  overflowX: 'auto',
  overflowY: 'hidden',
  paddingBottom: vars.space['0.5'],
  // Quiet, thin scrollbar; non-essential affordance.
  scrollbarWidth: 'thin',
});

export const thumb = style({
  flexShrink: 0,
  width: '52px',
  height: '52px',
  padding: 0,
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.tile,
  overflow: 'hidden',
  cursor: 'pointer',
  backgroundColor: vars.color.sunken,
  opacity: 0.6,
  transition: `opacity ${vars.motion.durFast} ${vars.motion.easeOut}, border-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { opacity: 1, borderColor: vars.color.line2 },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none', opacity: 1 },
  },
});

export const thumbActive = style({
  opacity: 1,
  borderColor: vars.color.accent,
  boxShadow: `inset 0 0 0 1px ${vars.color.accent}`,
});

export const thumbImg = style({
  width: '100%',
  height: '100%',
  objectFit: 'cover',
  display: 'block',
});
