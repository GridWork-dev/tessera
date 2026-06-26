import { globalStyle } from '@vanilla-extract/css';
import { themeClass } from '../theme.css';
import { lightClass } from './light.css';
import { obsidianCoolClass } from './obsidian-cool.css';
import { slateWarmClass } from './slate-warm.css';

// `color-scheme` so native form controls + scrollbars match the surface ramp.
// Dark themes -> dark UA chrome; the light theme -> light UA chrome.
// MUST live in a `.css.ts` file: globalStyle is a build-time style API and throws
// "styles outside a .css.ts context" at runtime if called from a plain `.ts`.
globalStyle(`.${themeClass}, .${slateWarmClass}, .${obsidianCoolClass}`, {
  colorScheme: 'dark',
});
globalStyle(`.${lightClass}`, {
  colorScheme: 'light',
});
