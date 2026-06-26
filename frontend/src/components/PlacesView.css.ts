import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   Places — page chrome (command bar, gridRegion, empty/loading
   states) is the SHARED workspace vocabulary (workspace.css).
   This file owns only the Places-specific surface: the place
   list/grid (no map dependency — a clean roster is enough and
   keeps the page fully offline).
   ============================================================ */

export const pad = style({
  padding: vars.space['4'],
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['3'],
});

export const countNote = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  fontVariantNumeric: 'tabular-nums',
});

export const grid = style({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
  gap: vars.space['3'],
});

export const card = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['3'],
  padding: vars.space['3'],
  borderRadius: vars.radius.tile,
  border: `1px solid ${vars.color.hair}`,
  background: vars.color.panel,
});

export const cardIcon = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  flexShrink: 0,
  width: '32px',
  height: '32px',
  borderRadius: vars.radius.button,
  background: vars.color.surface,
  color: vars.color.fore3,
});

export const cardText = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space['0.5'],
  flex: 1,
  minWidth: 0,
});

export const cardName = style({
  fontSize: vars.fontSize.meta,
  color: vars.color.fore,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const cardRegion = style({
  fontSize: vars.fontSize.micro,
  color: vars.color.fore3,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const cardCount = style({
  flexShrink: 0,
  fontFamily: vars.font.mono,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore2,
  fontVariantNumeric: 'tabular-nums',
});

// Inline code in copy (empty-state hints). Stays in the single UI font instead
// of falling back to the browser monospace default.
export const codeInline = style({
  fontFamily: vars.font.sans,
  fontSize: vars.fontSize.meta,
  color: vars.color.fore3,
  backgroundColor: vars.color.surface,
  borderRadius: vars.radius.small,
  padding: '0 4px',
});
