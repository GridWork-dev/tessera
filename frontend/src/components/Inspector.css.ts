import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   Inspector-local styles. Co-located with Inspector.tsx.
   Shared primitives (inspector shell, header, meta grid, chips,
   group labels, state blocks) are imported from workspace.css;
   only Inspector-specific pieces live here.
   ============================================================ */

/* ---- Preview (full-res with placeholder fallback) ---- */

export const preview = style({
  position: 'relative',
  width: '100%',
  aspectRatio: '1 / 1',
  flexShrink: 0,
  backgroundColor: vars.color.sunken,
  borderBottom: `1px solid ${vars.color.hair}`,
});

export const previewImg = style({
  width: '100%',
  height: '100%',
  objectFit: 'contain',
  display: 'block',
});

export const previewPlaceholder = style({
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space['2'],
  width: '100%',
  height: '100%',
  // Container color drives the ImageOff glyph (fore4 — icons are AA-exempt); the
  // readable copy overrides to fore3 below so it clears AA-normal.
  color: vars.color.fore4,
  fontSize: vars.fontSize.meta,
});

// The placeholder's text label (readable) — fore3 to clear AA-normal.
export const previewPlaceholderText = style({
  color: vars.color.fore3,
});

/* ---- Header controls (depth toggle lives beside the close button) ---- */

export const headerControls = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
});

/* Visually-hidden but screen-reader-available (e.g. the toggle's <legend>). */
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

/* Segmented basic/detailed toggle (a <fieldset> with reset chrome). */
export const depthToggle = style({
  display: 'inline-flex',
  alignItems: 'center',
  padding: vars.space['0.5'],
  margin: 0,
  gap: vars.space['0.5'],
  minInlineSize: 'auto', // override the UA fieldset min-width
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.button,
});

export const depthSeg = style({
  appearance: 'none',
  border: 'none',
  background: 'none',
  cursor: 'pointer',
  height: '22px',
  padding: `0 ${vars.space['2']}`,
  borderRadius: vars.radius.small,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.med,
  color: vars.color.fore3,
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { color: vars.color.fore2 },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});

export const depthSegActive = style({
  backgroundColor: vars.color.surface,
  color: vars.color.fore,
  selectors: {
    '&:hover': { color: vars.color.fore },
  },
});

/* ---- Section container (groups inside the body) ---- */

export const section = style({
  display: 'flex',
  flexDirection: 'column',
});

/* Top row of a section: label + optional trailing count. */
export const sectionHead = style({
  display: 'flex',
  alignItems: 'baseline',
  justifyContent: 'space-between',
  gap: vars.space['2'],
  marginBottom: vars.space['2'],
});

export const sectionCount = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
});

/* ---- Triage row (keep / maybe / reject) ---- */

export const triageRow = style({
  display: 'grid',
  gridTemplateColumns: 'repeat(3, 1fr)',
  gap: vars.space['1'],
});

export const triageBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space['1.5'],
  height: vars.size.controlMd,
  padding: `0 ${vars.space['2']}`,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}, border-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
    '&:disabled': { cursor: 'default', color: vars.color.disabledFore },
  },
});

/* Active triage state — semantic color per action, kept as data not chrome:
   a tinted fill + matching border + foreground. Color set inline per action. */
export const triageBtnActive = style({
  fontWeight: vars.fontWeight.semi,
});

/* ---- Inline error (flag failure) ---- */

export const errorBox = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  marginTop: vars.space['2'],
  padding: `${vars.space['2']} ${vars.space['3']}`,
  backgroundColor: vars.color.negBg,
  border: `1px solid ${vars.color.negLine}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore,
  fontSize: vars.fontSize.meta,
  lineHeight: vars.lineHeight.snug,
});

/* ---- Tag groups (category -> chips) ---- */

export const tagGroups = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['3'],
});

export const tagGroup = style({});

export const tagGroupLabel = style({
  display: 'flex',
  alignItems: 'baseline',
  gap: vars.space['2'],
  marginBottom: vars.space['1'],
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.semi,
  textTransform: 'capitalize',
  color: vars.color.fore3,
});

export const tagSource = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
  textTransform: 'none',
});

/* ---- Captions ---- */

export const captionList = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const captionItem = style({
  padding: `${vars.space['2']} ${vars.space['3']}`,
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.button,
});

export const captionModel = style({
  display: 'block',
  marginBottom: vars.space['1'],
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
});

export const captionText = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore,
  lineHeight: vars.lineHeight.snug,
});

/* ---- Notes ---- */

export const notesBox = style({
  padding: `${vars.space['2']} ${vars.space['3']}`,
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.button,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore2,
  lineHeight: vars.lineHeight.snug,
  whiteSpace: 'pre-wrap',
  overflowWrap: 'anywhere',
});

/* ---- User labels (add + removable chips) ---- */

export const labelForm = style({
  display: 'flex',
  gap: vars.space['1'],
  marginTop: vars.space['2'],
});

export const labelInput = style({
  flex: 1,
  minWidth: 0,
  height: vars.size.controlSm,
  padding: `0 ${vars.space['2']}`,
  backgroundColor: vars.color.sunken,
  border: `1px solid ${vars.color.line2}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  outline: 'none',
  transition: `border-color ${vars.motion.durFast} ${vars.motion.easeOut}, box-shadow ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&::placeholder': { color: vars.color.fore3 },
    '&:focus': { borderColor: vars.color.accent2, boxShadow: vars.shadow.focus },
  },
});

export const labelAddBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  height: vars.size.controlSm,
  padding: `0 ${vars.space['3']}`,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.line}`,
  borderRadius: vars.radius.button,
  color: vars.color.fore2,
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
    '&:disabled': {
      backgroundColor: vars.color.disabledBg,
      color: vars.color.disabledFore,
      cursor: 'default',
    },
  },
});

/* A user label chip with an inline remove control. */
export const labelChip = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
  height: '22px',
  padding: `0 4px 0 ${vars.space['2']}`,
  borderRadius: vars.radius.button,
  backgroundColor: vars.color.accentWeak,
  border: `1px solid ${vars.color.accent2}`,
  color: vars.color.fore,
  fontSize: vars.fontSize.micro,
});

export const labelChipText = style({
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  maxWidth: '18ch',
});

export const labelRemove = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '16px',
  height: '16px',
  padding: 0,
  background: 'none',
  border: 'none',
  borderRadius: vars.radius.small,
  color: vars.color.fore3,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}, color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});

/* ---- Similar strip (4-up clickable thumbs) ---- */

export const similarGrid = style({
  display: 'grid',
  gridTemplateColumns: 'repeat(4, 1fr)',
  gap: vars.space['1'],
});

export const similarTile = style({
  position: 'relative',
  aspectRatio: '1 / 1',
  overflow: 'hidden',
  padding: 0,
  background: 'none',
  border: `1px solid ${vars.color.hair}`,
  borderRadius: vars.radius.tile,
  cursor: 'pointer',
  transition: `border-color ${vars.motion.durFast} ${vars.motion.easeOut}, box-shadow ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { borderColor: vars.color.line2 },
    '&:focus-visible': {
      boxShadow: vars.shadow.focus,
      outline: 'none',
      borderColor: vars.color.accent,
    },
  },
});

export const similarImg = style({
  width: '100%',
  height: '100%',
  objectFit: 'cover',
  display: 'block',
  backgroundColor: vars.color.sunken,
});

/* ---- NudeNet region labels (data, neutral chrome) ---- */

export const nudeChip = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1.5'],
  height: '20px',
  padding: `0 ${vars.space['2']}`,
  borderRadius: vars.radius.button,
  backgroundColor: vars.color.surface,
  border: `1px solid ${vars.color.hair}`,
  color: vars.color.fore2,
  fontSize: vars.fontSize.micro,
});

export const nudeScore = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  color: vars.color.fore4,
});
