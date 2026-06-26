import { globalStyle, keyframes, style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

// Training / triage mode — a distraction-free, keyboard-first full-viewport
// surface for rapid one-at-a-time keep/reject/maybe + rating triage of the
// backlog. Its own route, so it owns the whole viewport.

export const root = style({
  position: 'fixed',
  inset: 0,
  display: 'grid',
  gridTemplateRows: 'auto 1fr auto',
  backgroundColor: vars.color.void,
  color: vars.color.fore,
});

// ---- Top bar: exit, queue config, progress -------------------------------

export const topBar = style({
  display: 'flex',
  alignItems: 'center',
  // Wrap (don't overflow) on narrow viewports — the row holds exit + title +
  // subtitle + the queue segments + progress, which exceed a phone's width.
  // `minHeight` (not fixed) lets it grow; the subtitle hides below 720px.
  flexWrap: 'wrap',
  gap: vars.space[3],
  minHeight: vars.size.barH,
  paddingBlock: vars.space[2],
  paddingInline: vars.space[5],
  borderBottom: `1px solid ${vars.color.hair}`,
  backgroundColor: vars.color.panel,
});

export const exitLink = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[2],
  height: '34px',
  padding: `0 ${vars.space[3]}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line2}`,
  backgroundColor: vars.color.surface,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  textDecoration: 'none',
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore },
  },
});

export const title = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.heading,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore,
  letterSpacing: vars.letterSpacing.tight,
  whiteSpace: 'nowrap',
});

export const subtitle = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  // Secondary helper text — drop it before the controls reflow on small screens.
  '@media': {
    '(max-width: 720px)': { display: 'none' },
  },
});

export const spacer = style({ flex: 1 });

// Queue-source toggle (untagged / unrated)
export const segGroup = style({
  display: 'inline-flex',
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line2}`,
  overflow: 'hidden',
});

export const segBtn = style({
  appearance: 'none',
  height: '34px',
  padding: `0 ${vars.space[3]}`,
  border: 'none',
  borderRight: `1px solid ${vars.color.line2}`,
  backgroundColor: vars.color.surface,
  color: vars.color.fore3,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:last-child': { borderRight: 'none' },
    '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore },
  },
});

export const segBtnActive = style({
  backgroundColor: vars.color.accentWeak,
  color: vars.color.accent,
  selectors: {
    '&:hover': { backgroundColor: vars.color.accentWeak, color: vars.color.accent },
  },
});

// Progress counter — mono numerics, tabular
export const progress = style({
  display: 'inline-flex',
  alignItems: 'baseline',
  gap: vars.space[2],
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  fontVariantNumeric: 'tabular-nums',
  color: vars.color.fore2,
});

export const progressNum = style({
  color: vars.color.fore,
  fontWeight: vars.fontWeight.semi,
});

export const progressTotal = style({ color: vars.color.fore3 });

// ---- Stage: the single large image + its quiet metadata ------------------

export const stage = style({
  position: 'relative',
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr)',
  alignItems: 'center',
  justifyItems: 'center',
  minHeight: 0,
  padding: vars.space[6],
  overflow: 'hidden',
});

// Thin top progress rail — quiet, full width of the stage
export const railTrack = style({
  position: 'absolute',
  top: 0,
  left: 0,
  right: 0,
  height: '2px',
  backgroundColor: vars.color.hair,
});

export const railFill = style({
  height: '100%',
  width: '100%',
  transformOrigin: 'left center',
  backgroundColor: vars.color.accent,
  // Determinate progress fill: scaleX (compositor-only) instead of width to
  // avoid layout thrash; the rail has no children to skew.
  transition: `transform ${vars.motion.durBase} ${vars.motion.easeOut}`,
});

export const imageWrap = style({
  position: 'relative',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '100%',
  height: '100%',
  minHeight: 0,
});

export const image = style({
  maxWidth: '100%',
  maxHeight: '100%',
  objectFit: 'contain',
  borderRadius: vars.radius.tile,
  backgroundColor: vars.color.sunken,
  userSelect: 'none',
});

// A flag badge that pulses in after an action, then fades — confirms the verb
const popIn = keyframes({
  '0%': { opacity: 0, transform: 'translate(-50%, 4px) scale(0.96)' },
  '15%': { opacity: 1, transform: 'translate(-50%, 0) scale(1)' },
  '80%': { opacity: 1, transform: 'translate(-50%, 0) scale(1)' },
  '100%': { opacity: 0, transform: 'translate(-50%, 0) scale(1)' },
});

export const actionFlash = style({
  position: 'absolute',
  top: vars.space[4],
  left: '50%',
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[2],
  padding: `${vars.space[2]} ${vars.space[4]}`,
  borderRadius: vars.radius.pill,
  border: `1px solid ${vars.color.line2}`,
  backgroundColor: vars.color.panel2,
  color: vars.color.fore,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.semi,
  boxShadow: vars.shadow.pop,
  animation: `${popIn} 900ms ${vars.motion.easeOut} forwards`,
  pointerEvents: 'none',
});

globalStyle(`${actionFlash} svg`, { display: 'block' });

// ---- Sidecar: quiet metadata column to the right of the image ------------

export const sidecar = style({
  position: 'absolute',
  top: vars.space[6],
  right: vars.space[6],
  width: '260px',
  maxHeight: `calc(100% - ${vars.space[8]})`,
  overflowY: 'auto',
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space[4],
  padding: vars.space[4],
  borderRadius: vars.radius.panel,
  border: `1px solid ${vars.color.hair}`,
  backgroundColor: vars.color.panel,
  // Restrained: the sidecar never competes with the image; soft, never glassy.
  '@media': {
    '(max-width: 920px)': { display: 'none' },
  },
});

export const sidecarRow = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space[1],
});

export const groupLabel = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore3,
});

export const metaGrid = style({
  display: 'grid',
  gridTemplateColumns: 'auto 1fr',
  columnGap: vars.space[3],
  rowGap: vars.space[2],
  alignItems: 'baseline',
});

export const metaKey = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
});

export const metaVal = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore,
  wordBreak: 'break-word',
});

export const metaNum = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  fontVariantNumeric: 'tabular-nums',
  color: vars.color.fore,
  textAlign: 'right',
});

export const tagWrap = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space[2],
});

export const tag = style({
  display: 'inline-flex',
  alignItems: 'center',
  height: vars.size.controlXs,
  padding: `0 ${vars.space[2]}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.hair}`,
  backgroundColor: vars.color.surface,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.label,
});

export const muted = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore4,
});

export const errorText = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  color: vars.color.nsfw,
});

// ---- Action bar: the keyboard legend made tangible ------------------------

export const actionBar = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  flexWrap: 'wrap',
  gap: vars.space[3],
  padding: `${vars.space[4]} ${vars.space[5]}`,
  borderTop: `1px solid ${vars.color.hair}`,
  backgroundColor: vars.color.panel,
});

export const verbGroup = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space[2],
});

// A verb button = an action + its hotkey. The kbd is part of the affordance.
export const verbBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[2],
  height: '40px',
  padding: `0 ${vars.space[4]}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line2}`,
  backgroundColor: vars.color.surface,
  color: vars.color.fore,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, border-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { backgroundColor: vars.color.hover },
    '&:disabled': {
      backgroundColor: vars.color.disabledBg,
      color: vars.color.disabledFore,
      borderColor: vars.color.hair,
      cursor: 'not-allowed',
    },
  },
});

// Active state for the verb matching the current image's flag/rating.
export const verbBtnActive = style({
  borderColor: vars.color.accent2,
  backgroundColor: vars.color.active,
  color: vars.color.fore,
});

globalStyle(`${verbBtn} svg`, { display: 'block', flexShrink: 0 });

export const kbd = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  minWidth: '18px',
  height: '18px',
  padding: `0 ${vars.space[1]}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line2}`,
  backgroundColor: vars.color.sunken,
  color: vars.color.fore3,
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  fontVariantNumeric: 'tabular-nums',
  lineHeight: 1,
});

export const divider = style({
  width: '1px',
  alignSelf: 'stretch',
  margin: `${vars.space[1]} ${vars.space[2]}`,
  backgroundColor: vars.color.line,
});

// Small rating dot inside a verb button (semantic data color)
export const ratingDot = style({
  width: '8px',
  height: '8px',
  borderRadius: vars.radius.pill,
  flexShrink: 0,
});

// ---- Reject reason chips (contextual row, shown only after a reject) -------

export const reasonRow = style({
  position: 'absolute',
  left: '50%',
  bottom: vars.space[5],
  transform: 'translateX(-50%)',
  display: 'flex',
  alignItems: 'center',
  flexWrap: 'wrap',
  justifyContent: 'center',
  gap: vars.space[2],
  maxWidth: '90%',
  padding: `${vars.space[2]} ${vars.space[3]}`,
  borderRadius: vars.radius.panel,
  border: `1px solid ${vars.color.line2}`,
  backgroundColor: vars.color.panel2,
  boxShadow: vars.shadow.pop,
});

export const reasonLabel = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.semi,
  textTransform: 'uppercase',
  letterSpacing: vars.letterSpacing.label,
  color: vars.color.nsfw,
  marginRight: vars.space[1],
});

export const reasonChip = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[2],
  height: '30px',
  padding: `0 ${vars.space[3]}`,
  borderRadius: vars.radius.pill,
  border: `1px solid ${vars.color.line2}`,
  backgroundColor: vars.color.surface,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, border-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore },
  },
});

export const reasonChipActive = style({
  borderColor: vars.color.accent2,
  backgroundColor: vars.color.accentWeak,
  color: vars.color.accent,
  selectors: {
    '&:hover': { backgroundColor: vars.color.accentWeak, color: vars.color.accent },
  },
});

export const navBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[2],
  height: '40px',
  padding: `0 ${vars.space[3]}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line2}`,
  backgroundColor: vars.color.surface,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:disabled': {
      backgroundColor: vars.color.disabledBg,
      color: vars.color.disabledFore,
      borderColor: vars.color.hair,
      cursor: 'not-allowed',
    },
  },
});

globalStyle(`${navBtn} svg`, { display: 'block' });

// ---- Centered states (empty / loading / error / done) ---------------------

export const stateWrap = style({
  position: 'absolute',
  inset: 0,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space[3],
  textAlign: 'center',
  padding: vars.space[6],
  color: vars.color.fore3,
});

export const stateTitle = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.display,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore,
});

export const stateHint = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  maxWidth: '42ch',
  lineHeight: vars.lineHeight.snug,
});
