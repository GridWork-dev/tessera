import { style } from '@vanilla-extract/css';
import { vars } from '../styles/contract.css';

/* ============================================================
   Shared app navigation — brand wordmark + primary route nav.
   Rendered inside every page's command bar (Browse, Videos,
   Dashboard) so the top-left chrome is IDENTICAL across routes.
   Flat accent glyph, no gradient/glow (impeccable). The nav
   icon-buttons reuse workspace `iconButton` / `iconButtonActive`.
   ============================================================ */

export const brandMark = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['2'],
  flexShrink: 0,
  // Explicit so the wordmark never inherits a stray font (it's identity-critical
  // and was the element that surfaced the old serif-fallback bug).
  fontFamily: vars.font.sans,
  color: vars.color.fore,
  fontSize: vars.fontSize.brand,
  fontWeight: vars.fontWeight.bold,
  letterSpacing: vars.letterSpacing.tight,
  textDecoration: 'none',
  userSelect: 'none',
  whiteSpace: 'nowrap',
  selectors: {
    '&:focus-visible': {
      boxShadow: vars.shadow.focus,
      outline: 'none',
      borderRadius: vars.radius.small,
    },
  },
});

// The Pigment tessera mark — a jade tile (currentColor = accent); the facet line
// is translucent black inside the SVG so it reads on any theme accent.
export const brandGlyph = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '22px',
  height: '22px',
  flexShrink: 0,
  color: vars.color.accent,
});

// Whole wordmark is a single calm unit; the second word is muted via brandDim.
export const brandWord = style({ whiteSpace: 'nowrap' });

export const brandDim = style({
  color: vars.color.fore3,
  fontWeight: vars.fontWeight.med,
});

// Nav owns the spacing + the hairline gap from the brand; the buttons
// themselves are the shared workspace iconButton classes.
export const nav = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space['1'],
  flexShrink: 0,
  marginLeft: vars.space['2'],
});
