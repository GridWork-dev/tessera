import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   Command bar — top application header (height vars.size.barH).
   Left: brand wordmark + primary nav. Center: search. Right:
   sort, density toggle, inspector toggle, quiet asset figure.
   Calm, confident, single-row chrome — no hero metrics, no glow.
   ============================================================ */

/* Brand wordmark + primary nav now live in the shared AppNav component
   (AppNav.tsx / AppNav.css.ts) so the top-left chrome is identical on every
   page. CommandBar composes <AppNav /> and owns only the Browse-specific
   search + right cluster below. */

/* ---- Center: search ---- */

export const searchWrap = style({
  position: 'relative',
  flex: 1,
  minWidth: '160px',
  maxWidth: '520px',
});

export const searchInput = style({
  width: '100%',
  height: vars.size.controlLg,
  padding: `0 64px 0 36px`,
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore,
  fontSize: vars.fontSize.heading,
  fontFamily: vars.font.sans,
  outline: 'none',
  transition: `border-color ${vars.motion.durFast} ${vars.motion.easeOut}, box-shadow ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&::placeholder': { color: vars.color.fore3 },
    '&:focus': { borderColor: vars.color.accent2, boxShadow: vars.shadow.focus },
    // Hide the native search clear affordance — we own clearing via Escape.
    '&::-webkit-search-cancel-button': { WebkitAppearance: 'none', appearance: 'none' },
  },
});

export const searchIcon = style({
  position: 'absolute',
  left: vars.space['3'],
  top: '50%',
  transform: 'translateY(-50%)',
  color: vars.color.fore3,
  pointerEvents: 'none',
});

export const kbdHint = style({
  position: 'absolute',
  right: vars.space['2'],
  top: '50%',
  transform: 'translateY(-50%)',
  display: 'flex',
  gap: vars.space['0.5'],
  pointerEvents: 'none',
  transition: `opacity ${vars.motion.durFast} ${vars.motion.easeOut}`,
});

// Fade the ⌘K hint out once the field is focused or has content — it has served
// its purpose and would otherwise collide with typed text.
export const kbdHintHidden = style({ opacity: 0 });

export const kbd = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore3,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.small,
  padding: `1px ${vars.space['1.5']}`,
  lineHeight: vars.lineHeight.tight,
});

/* ---- Search-mode segmented control (Tags / Caption / Semantic) ---- */

export const modeSegment = style({
  display: 'inline-flex',
  alignItems: 'center',
  padding: vars.space['0.5'],
  gap: vars.space['0.5'],
  flexShrink: 0,
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
});

export const modeSegmentBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  height: vars.size.controlSm,
  padding: `0 ${vars.space['2']}`,
  color: vars.color.fore3,
  backgroundColor: 'transparent',
  border: 'none',
  borderRadius: vars.radius.small,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  whiteSpace: 'nowrap',
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not([aria-pressed="true"])': { color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});

export const modeSegmentBtnActive = style({
  color: vars.color.accent,
  backgroundColor: vars.color.accentWeak,
});

/* ---- Right cluster ---- */

export const spacer = style({ flex: '0 1 16px' });

export const rightCluster = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  flexShrink: 0,
});

// A grouped 1px hairline divider between functional clusters.
export const divider = style({
  width: '1px',
  height: '20px',
  backgroundColor: vars.color.line,
  flexShrink: 0,
});

/* Square icon-button: the shared app-wide vocabulary lives in workspace.css
   (one recipe, full hover/active/focus/disabled state set). Re-exported here so
   this component's `css.iconButton` references resolve to the single source. */
export { iconButton, iconButtonActive } from '../styles/workspace.css';

/* ---- Sort control (native select, styled chrome) ---- */

export const sortWrap = style({
  position: 'relative',
  display: 'inline-flex',
  alignItems: 'center',
});

export const sortIcon = style({
  position: 'absolute',
  left: vars.space['2'],
  top: '50%',
  transform: 'translateY(-50%)',
  color: vars.color.fore3,
  pointerEvents: 'none',
});

export const sortSelect = style({
  appearance: 'none',
  WebkitAppearance: 'none',
  MozAppearance: 'none',
  height: vars.size.controlMd,
  padding: `0 ${vars.space['4']} 0 30px`,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  cursor: 'pointer',
  outline: 'none',
  transition: `border-color ${vars.motion.durFast} ${vars.motion.easeOut}, background-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, borderColor: vars.color.accent2 },
  },
});

export const sortCaret = style({
  position: 'absolute',
  right: vars.space['2'],
  top: '50%',
  transform: 'translateY(-50%)',
  color: vars.color.fore3,
  pointerEvents: 'none',
});

/* ---- Density segmented control ---- */

export const segment = style({
  display: 'inline-flex',
  alignItems: 'center',
  padding: vars.space['0.5'],
  gap: vars.space['0.5'],
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
});

export const segmentBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '28px',
  height: vars.size.controlXs,
  color: vars.color.fore3,
  backgroundColor: 'transparent',
  border: 'none',
  borderRadius: vars.radius.small,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not([aria-pressed="true"])': { color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});

export const segmentBtnActive = style({
  color: vars.color.accent,
  backgroundColor: vars.color.accentWeak,
});

/* ---- Quiet asset figure (inline, NOT a hero metric) ---- */

export const figure = style({
  display: 'inline-flex',
  alignItems: 'baseline',
  gap: vars.space['1.5'],
  flexShrink: 0,
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore2,
  whiteSpace: 'nowrap',
  fontVariantNumeric: 'tabular-nums',
});

export const figureCount = style({
  color: vars.color.fore2,
  fontVariantNumeric: 'tabular-nums',
});

export const figureUnit = style({
  color: vars.color.fore3,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.label,
});
