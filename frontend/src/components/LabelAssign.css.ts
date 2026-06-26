import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* Label assignment UI (Wave 2b). One block per label set: single-select renders
   a segmented row, multi-select a chip toggle group. Label colors are DATA
   (applied inline via labelChipStyle), never theme tokens — these styles own
   only layout + the neutral (unselected) chrome. */

export const sets = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['4'],
});

export const set = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const setLabel = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  fontSize: vars.fontSize.label,
  color: vars.color.fore3,
  letterSpacing: vars.letterSpacing.label,
});

export const valueWrap = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space['2'],
});

/** A value chip in its neutral (unselected) state. Selected chips get the data
 *  color inline; this provides the base shape + the unselected surface. */
export const chip = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1'],
  height: vars.size.controlXs,
  padding: `0 ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line2}`,
  background: vars.color.surface,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
  cursor: 'pointer',
  transition: `background ${vars.motion.durFast}, border-color ${vars.motion.durFast}`,
  selectors: {
    '&:hover': { background: vars.color.hover },
    '&:disabled': { cursor: 'default', color: vars.color.disabledFore },
  },
});

/** Marker for a selected chip whose color comes from the DATA color inline; a
 *  ring keeps the selection legible even when the data color is subtle. */
export const chipSelected = style({
  borderColor: vars.color.fore3,
  fontWeight: vars.fontWeight.med,
});

export const empty = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore4,
});
