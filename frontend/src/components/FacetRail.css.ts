import { keyframes, style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   FacetRail — co-located styles. The generic rail chrome
   (rail / railHeader / section / facetRow / facetCount …) lives
   in workspace.css; this file only adds what's specific to the
   rail's controls: the processed segmented control and the
   collapsible category headers (Radix Collapsible).
   ============================================================ */

/* ---- Label-set facet value dot (color is DATA, applied inline) ---- */

export const labelDot = style({
  display: 'inline-block',
  width: '8px',
  height: '8px',
  borderRadius: vars.radius.pill,
  marginRight: vars.space['2'],
  flexShrink: 0,
  // Neutral hairline so a value with no data color still reads as a dot.
  border: `1px solid ${vars.color.line2}`,
  verticalAlign: 'middle',
});

/* ---- Processed (all / tagged / untagged) segmented control ---- */

export const segmentWrap = style({
  display: 'flex',
  gap: vars.space['0.5'],
  minWidth: 0,
  padding: vars.space['1'],
  margin: `${vars.space['3']} ${vars.space['4']}`,
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.button,
});

export const segment = style({
  flex: 1,
  minHeight: '26px',
  padding: `0 ${vars.space['2']}`,
  background: 'none',
  border: '1px solid transparent',
  borderRadius: vars.radius.small,
  color: vars.color.fore3,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.med,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});

export const segmentActive = style({
  backgroundColor: vars.color.surface,
  color: vars.color.fore,
  borderColor: vars.color.line2,
});

// Visually-hidden — gives the segmented <fieldset> an accessible name via its
// <legend> without rendering visible chrome.
export const srOnly = style({
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: 0,
  margin: '-1px',
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  border: 0,
});

/* ---- Collapsible category sections (Radix Collapsible) ---- */

// One section = a Collapsible.Root. The bottom hairline lives here so the
// divider tracks the section whether open or collapsed.
export const collapsible = style({
  borderBottom: `1px solid ${vars.color.hair}`,
});

// Trigger styled as a clickable group header — a real <button>, so the global
// focus ring applies. Reuses the sectionLabel look plus our chevron + a count.
export const trigger = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  width: '100%',
  padding: `${vars.space['3']} ${vars.space['4']}`,
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  textAlign: 'left',
  userSelect: 'none',
  color: vars.color.fore3,
  transition: `color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { color: vars.color.fore2 },
    '&:focus-visible': {
      boxShadow: vars.shadow.focus,
      outline: 'none',
      borderRadius: vars.radius.small,
    },
  },
});

export const triggerLabel = style({
  flex: 1,
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.semi,
  textTransform: 'capitalize',
});

export const triggerCount = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
});

// Chevron rotates to point down when its trigger reports the open state. Radix
// sets data-state on the trigger element, which is the chevron's parent.
export const chevron = style({
  flexShrink: 0,
  color: vars.color.fore4,
  transition: `transform ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '[data-state="open"] > &': { transform: 'rotate(90deg)' },
  },
});

// Tighten the bottom padding of the values list inside an open section so it
// reads as one grouped block.
export const valueList = style({
  paddingBottom: vars.space['2'],
});

// Radix mounts/unmounts content; a brief height collapse keeps it from popping.
// Honors the global prefers-reduced-motion rule (collapses to ~0ms).
const slideDown = keyframes({
  from: { height: 0, opacity: 0 },
  to: { height: 'var(--radix-collapsible-content-height)', opacity: 1 },
});
const slideUp = keyframes({
  from: { height: 'var(--radix-collapsible-content-height)', opacity: 1 },
  to: { height: 0, opacity: 0 },
});

export const content = style({
  overflow: 'hidden',
  selectors: {
    '&[data-state="open"]': {
      animation: `${slideDown} ${vars.motion.durBase} ${vars.motion.easeOut}`,
    },
    '&[data-state="closed"]': {
      animation: `${slideUp} ${vars.motion.durBase} ${vars.motion.easeOut}`,
    },
  },
});
