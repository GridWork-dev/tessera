import type { ImageLabel } from '../api/types';

/**
 * Group an image's assigned labels into ``set_id -> (value -> labelId)``. The
 * inspector uses this to mark which value chips are active per set and to find
 * the row id to unassign. Pure so it is unit-testable without the DOM/query layer.
 */
/** K/M/R keyboard mnemonics → Rating-set value (plan Task B). Keep→sfw,
 *  Maybe→suggestive, Reject→nsfw — the three actionable tiers, mirroring the
 *  TrainingMode flag mnemonics applied to the user-rating set. Returns null for
 *  any other key. Pure so the inspector keyboard layer is unit-testable. */
export function ratingKeyToValue(key: string): string | null {
  switch (key.toLowerCase()) {
    case 'k':
      return 'sfw';
    case 'm':
      return 'suggestive';
    case 'r':
      return 'nsfw';
    default:
      return null;
  }
}

export function buildAssignedBySet(labels: ImageLabel[]): Map<number, Map<string, number>> {
  const out = new Map<number, Map<string, number>>();
  for (const lbl of labels) {
    const m = out.get(lbl.set_id) ?? new Map<string, number>();
    m.set(lbl.value, lbl.id);
    out.set(lbl.set_id, m);
  }
  return out;
}
