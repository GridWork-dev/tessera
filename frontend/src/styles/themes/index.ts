import { themeClass } from '../theme.css';
import { lightClass } from './light.css';
import { obsidianCoolClass } from './obsidian-cool.css';
import { slateWarmClass } from './slate-warm.css';
// Side-effect import: registers the per-theme `color-scheme` globalStyles. Must
// be a `.css.ts` (globalStyle is build-time only) — see color-scheme.css.ts.
import './color-scheme.css';

/** All selectable themes. Pigment (default) + two alternate darks + one light. */
export const THEMES = {
  pigment: themeClass,
  'slate-warm': slateWarmClass,
  'obsidian-cool': obsidianCoolClass,
  light: lightClass,
} as const;
export type ThemeId = keyof typeof THEMES;
export const THEME_IDS = Object.keys(THEMES) as ThemeId[];
export const DEFAULT_THEME: ThemeId = 'pigment';

/** Theme ids that use a light surface ramp (drives `color-scheme` + accent ink). */
export const LIGHT_THEME_IDS: ThemeId[] = ['light'];
export function isLightTheme(id: ThemeId): boolean {
  return LIGHT_THEME_IDS.includes(id);
}

export function themeClassName(id: ThemeId): string {
  return THEMES[id] ?? THEMES[DEFAULT_THEME];
}
