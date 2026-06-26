/**
 * Label colors are DATA, not theme tokens (DESIGN.md / spec 3.4): each label's
 * color comes from `label_definitions.color` and is applied inline at the chip,
 * never baked into a theme. These helpers turn a raw hex data color into an
 * AA-guarded chip style (tinted background + a readable foreground), degrading
 * to a neutral chip (no inline color, the surface token wins) for null/garbage.
 */

import type { CSSProperties } from 'react';

const HEX_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

/** Expand #rgb to #rrggbb; assumes a validated hex. */
function expand(hex: string): string {
  if (hex.length === 4) {
    const r = hex[1] ?? '0';
    const g = hex[2] ?? '0';
    const b = hex[3] ?? '0';
    return `#${r}${r}${g}${g}${b}${b}`;
  }
  return hex;
}

/** sRGB relative luminance (WCAG) of a validated #rrggbb color, 0..1. */
function luminance(hex: string): number {
  const full = expand(hex);
  const channel = (i: number): number => {
    const v = Number.parseInt(full.slice(1 + i * 2, 3 + i * 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
}

/**
 * Black or white foreground for legible text on a data background. Compares the
 * WCAG contrast ratio against black vs white and returns the higher-contrast
 * choice — guarantees the most readable text on any label color.
 */
export function readableOn(bg: string): '#000000' | '#ffffff' {
  if (!HEX_RE.test(bg)) return '#ffffff';
  const l = luminance(bg);
  const onBlack = (l + 0.05) / 0.05; // contrast vs black
  const onWhite = 1.05 / (l + 0.05); // contrast vs white
  return onBlack >= onWhite ? '#000000' : '#ffffff';
}

/**
 * Inline chip style for a label value's data color. A valid hex yields a filled
 * chip with an AA-readable foreground; null/empty/garbage yields an empty style
 * so the chip falls back to the neutral surface token (no color-only meaning).
 */
export function labelChipStyle(color: string | null | undefined): CSSProperties {
  if (!color || !HEX_RE.test(color)) return {};
  return { backgroundColor: color, color: readableOn(color) };
}
