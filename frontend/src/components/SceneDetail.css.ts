import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   SceneDetail — a right-side drawer (scrim + sliding panel) for
   one video's deep-scene enrichment. Left: the scene list with
   per-scene status flags. Right (selected): tags, caption,
   ordered transcript segments, face count, Re-enrich action.

   Standalone surface: VideosView opens it with a videoId (e.g.
   from a scene chip in the player). All chrome here is local; the
   empty/loading vocabulary is shared (workspace.css stateWrap).
   ============================================================ */

export const overlay = style({
  position: 'fixed',
  inset: 0,
  backgroundColor: vars.scrim.strong,
  display: 'flex',
  justifyContent: 'flex-end',
  zIndex: 110,
});

export const drawer = style({
  width: 'min(560px, 96vw)',
  height: '100%',
  background: vars.color.panel,
  borderLeft: `1px solid ${vars.color.line}`,
  boxShadow: vars.shadow.pop,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
});

export const header = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  padding: `${vars.space['3']} ${vars.space['4']}`,
  borderBottom: `1px solid ${vars.color.hair}`,
  background: vars.color.panel2,
});

export const headerTitle = style({
  flex: 1,
  minWidth: 0,
  fontSize: vars.fontSize.heading,
  fontWeight: vars.fontWeight.semi,
  color: vars.color.fore,
});

export const headerMeta = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  fontVariantNumeric: 'tabular-nums',
});

export const closeBtn = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '28px',
  height: vars.size.controlSm,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.line}`,
  background: vars.color.surface,
  color: vars.color.fore2,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover': { backgroundColor: vars.color.hover, color: vars.color.fore },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
  },
});

/* ---- Body: scrollable, sectioned ---- */

export const body = style({
  flex: 1,
  minHeight: 0,
  overflowY: 'auto',
  display: 'flex',
  flexDirection: 'column',
});

/* ---- Scene list (the per-video index of scenes) ---- */

export const sceneList = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['1'],
  padding: vars.space['3'],
});

export const sceneRow = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  width: '100%',
  padding: `${vars.space['2']} ${vars.space['3']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.hair}`,
  background: vars.color.surface,
  color: vars.color.fore2,
  cursor: 'pointer',
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

export const sceneRowActive = style({
  borderColor: vars.color.accent,
  background: vars.color.accentWeak,
});

export const sceneRowIndex = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  fontVariantNumeric: 'tabular-nums',
  color: vars.color.fore,
  minWidth: '3ch',
});

export const sceneRowTime = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  fontVariantNumeric: 'tabular-nums',
  color: vars.color.fore3,
  flex: 1,
});

export const statusFlags = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['1.5'],
});

export const flag = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: vars.fontSize.micro,
  lineHeight: 1,
  color: vars.color.fore4,
});

export const flagOn = style({
  color: vars.color.accent,
});

/* ---- Detail sections (tags / caption / transcript / faces) ---- */

export const detail = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['4'],
  padding: vars.space['4'],
  borderTop: `1px solid ${vars.color.hair}`,
});

export const section = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const sectionLabel = style({
  fontSize: vars.fontSize.label,
  fontWeight: vars.fontWeight.semi,
  letterSpacing: vars.letterSpacing.label,
  textTransform: 'uppercase',
  color: vars.color.fore3,
});

export const caption = style({
  fontSize: vars.fontSize.body,
  lineHeight: vars.lineHeight.snug,
  color: vars.color.fore2,
});

export const tagWrap = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space['2'],
});

export const tag = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
  padding: `${vars.space['0.5']} ${vars.space['2']}`,
  borderRadius: vars.radius.pill,
  border: `1px solid ${vars.color.line}`,
  background: vars.color.panel2,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
});

export const tagConf = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  fontVariantNumeric: 'tabular-nums',
  color: vars.color.fore4,
});

/* ---- Transcript ---- */

export const transcript = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['2'],
});

export const segment = style({
  display: 'grid',
  gridTemplateColumns: '64px 1fr',
  gap: vars.space['3'],
  alignItems: 'baseline',
});

export const segmentTime = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.micro,
  fontVariantNumeric: 'tabular-nums',
  color: vars.color.fore4,
  whiteSpace: 'nowrap',
});

export const segmentText = style({
  fontSize: vars.fontSize.meta,
  lineHeight: vars.lineHeight.snug,
  color: vars.color.fore2,
});

/* ---- Faces ---- */

export const faceCount = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['2'],
  fontSize: vars.fontSize.body,
  color: vars.color.fore2,
});

export const faceCountNum = style({
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.heading,
  fontWeight: vars.fontWeight.semi,
  fontVariantNumeric: 'tabular-nums',
  color: vars.color.fore,
});

/* ---- Empty / unenriched inline note ---- */

export const emptyNote = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  fontStyle: 'italic',
});

/* ---- Footer action bar (Re-enrich) ---- */

export const footer = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  padding: `${vars.space['3']} ${vars.space['4']}`,
  borderTop: `1px solid ${vars.color.hair}`,
  background: vars.color.panel2,
});

export const footerHint = style({
  flex: 1,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
});

export const action = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space['1.5'],
  padding: `${vars.space['2']} ${vars.space['4']}`,
  borderRadius: vars.radius.button,
  border: `1px solid ${vars.color.accent2}`,
  background: vars.color.accentWeak,
  color: vars.color.accent,
  fontSize: vars.fontSize.meta,
  fontWeight: vars.fontWeight.med,
  cursor: 'pointer',
  transition: `background-color ${vars.motion.durFast} ${vars.motion.easeOut}`,
  selectors: {
    '&:hover:not(:disabled)': { backgroundColor: vars.color.hover },
    '&:focus-visible': { boxShadow: vars.shadow.focus, outline: 'none' },
    '&:disabled': {
      cursor: 'default',
      borderColor: vars.color.line,
      background: vars.color.disabledBg,
      color: vars.color.disabledFore,
    },
  },
});

/* Confirmation pill after a backfill kicks off. */
export const started = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.accent,
});
