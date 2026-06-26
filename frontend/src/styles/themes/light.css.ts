import { createTheme } from '@vanilla-extract/css';
import { vars } from '../contract.css';
import { lightValues } from './light.values';

/**
 * LIGHT — the one light preset, filling the same Pigment contract as the dark
 * themes (theme.css.ts). A near-white surface ramp (floor #f4f5f7, layered light
 * panels up to pure-white tiles), an inverted text ramp (near-black fore down to
 * a still-readable fore4), retuned shadows/scrims/weak tints, and the jade signal
 * kept as the brand — darkened to #0c8462 so it clears WCAG AA on light.
 *
 * The token VALUES live in `light.values.ts` (a plain object, importable by the
 * contrast test); this file only binds them to the contract via `createTheme`.
 * Built from the Pigment shape with surface/text/accent/rating/scrim/shadow
 * deltas; structural tokens (radius/space/size/font/motion) stay IDENTICAL across
 * themes.
 *
 * WCAG AA — enforced by `light.contrast.test.ts`, summarized here:
 *   fore/fore2/fore3 : AA-normal (>=4.5:1) on every surface (min 4.69 @active).
 *   fore4            : AA-normal on the surfaces its micro-counts sit on
 *                      (void/sunken/panel/panel2/surface, min 4.69); never body.
 *   accent (#0c8462) : >=3.73:1 UI/non-text on every surface (incl. active/sunken).
 *   onAccent (#fff)  : 4.67:1 on the jade fill — full AA-normal button labels.
 *   rating colors    : >=4.5:1 as label TEXT on the primary surfaces.
 *
 * `color-scheme: light` (set on this class in themes/color-scheme.css.ts) makes
 * native form controls + scrollbars render light to match.
 */
export const lightClass = createTheme(vars, lightValues);
