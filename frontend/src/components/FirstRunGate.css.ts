import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   First-run gate fallback banner. A thin, fixed strip pinned to
   the top edge that appears only when the /api/setup/status probe
   fails — so a genuine first-run user is never stranded on a blank
   app with no way to reach the wizard. Pigment tokens only.
   ============================================================ */

export const banner = style({
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  zIndex: 1000,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space['3'],
  padding: `${vars.space['2']} ${vars.space['4']}`,
  background: vars.color.negBg,
  borderBottom: `1px solid ${vars.color.negLine}`,
  color: vars.color.fore2,
  fontSize: vars.fontSize.meta,
  lineHeight: vars.lineHeight.snug,
});

export const action = style({
  color: vars.color.accent,
  fontWeight: vars.fontWeight.semi,
  textDecoration: 'none',
  selectors: {
    '&:hover': { textDecoration: 'underline' },
  },
});
