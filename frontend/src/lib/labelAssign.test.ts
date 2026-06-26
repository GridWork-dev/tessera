import { describe, expect, it } from 'vitest';
import type { ImageLabel } from '../api/types';
import { buildAssignedBySet, ratingKeyToValue } from './labelAssign';

const lbl = (id: number, set_id: number, value: string): ImageLabel => ({
  id,
  image_id: 1,
  set_id,
  category: 'x',
  value,
});

describe('buildAssignedBySet', () => {
  it('groups assignments by set and maps value -> labelId', () => {
    const m = buildAssignedBySet([lbl(10, 1, 'sfw'), lbl(11, 2, 'calm'), lbl(12, 2, 'tense')]);
    expect(m.get(1)?.get('sfw')).toBe(10);
    expect(m.get(2)?.get('calm')).toBe(11);
    expect(m.get(2)?.get('tense')).toBe(12);
  });

  it('a single-select set holds exactly one value (server replaces prior)', () => {
    // After a single-select replace, only the new row remains for that set.
    const m = buildAssignedBySet([lbl(20, 1, 'nsfw')]);
    expect([...(m.get(1)?.keys() ?? [])]).toEqual(['nsfw']);
  });

  it('a multi-select set accumulates several values', () => {
    const m = buildAssignedBySet([lbl(30, 3, 'a'), lbl(31, 3, 'b')]);
    expect(new Set(m.get(3)?.keys())).toEqual(new Set(['a', 'b']));
  });

  it('empty input -> empty map', () => {
    expect(buildAssignedBySet([]).size).toBe(0);
  });
});

describe('ratingKeyToValue', () => {
  it('maps K/M/R (any case) to the Rating tiers', () => {
    expect(ratingKeyToValue('k')).toBe('sfw');
    expect(ratingKeyToValue('K')).toBe('sfw');
    expect(ratingKeyToValue('m')).toBe('suggestive');
    expect(ratingKeyToValue('M')).toBe('suggestive');
    expect(ratingKeyToValue('r')).toBe('nsfw');
    expect(ratingKeyToValue('R')).toBe('nsfw');
  });

  it('returns null for any other key', () => {
    for (const k of ['a', 'x', '1', 'Enter', 'ArrowRight', ' ']) {
      expect(ratingKeyToValue(k)).toBeNull();
    }
  });
});
