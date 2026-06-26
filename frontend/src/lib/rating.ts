import { vars } from '../styles/contract.css';

// Rating → token + label. Color is always reinforced by a text label (never
// color alone) per the accessibility principle in PRODUCT.md.
//
// MECHANISM (pinned by rating.test.ts): rating color is a SEMANTIC THEME TOKEN
// (`vars.color.*`, DESIGN.md "rating colors, semantic data, never chrome"),
// applied via plain inline style. It is deliberately NOT the data-driven label
// path: it does not read `label_definitions.color` and is not delivered via
// `assignInlineVars`. Per-label data colors (AA-guarded) live in labelColor.ts.

export function ratingColor(rating: string | null): string {
  switch (rating) {
    case 'sfw':
      return vars.color.sfw;
    case 'suggestive':
      return vars.color.sugg;
    case 'nsfw':
      return vars.color.nsfw;
    default:
      return vars.color.unrated;
  }
}

export function ratingWeak(rating: string | null): string {
  switch (rating) {
    case 'sfw':
      return vars.color.sfwWeak;
    case 'suggestive':
      return vars.color.suggWeak;
    case 'nsfw':
      return vars.color.nsfwWeak;
    default:
      return 'transparent';
  }
}

export function ratingLabel(rating: string | null): string {
  switch (rating) {
    case 'sfw':
      return 'SFW';
    case 'suggestive':
      return 'SUGG';
    case 'nsfw':
      return 'NSFW';
    default:
      return 'UNRATED';
  }
}

export const RATINGS = ['sfw', 'suggestive', 'nsfw', 'unrated'] as const;
