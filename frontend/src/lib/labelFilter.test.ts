import { describe, expect, it } from 'vitest';
import { hasLabels, labelsToParams, selectLabel, toggleLabel } from './labelFilter';

describe('labelFilter', () => {
  it('flattens a selection to sorted set:value params', () => {
    expect(labelsToParams({ Rating: ['nsfw'], Mood: ['tense', 'calm'] })).toEqual([
      'Mood:calm',
      'Mood:tense',
      'Rating:nsfw',
    ]);
  });

  it('empty selection -> empty params', () => {
    expect(labelsToParams({})).toEqual([]);
  });

  it('toggles a value in (OR within a set)', () => {
    expect(toggleLabel({}, 'Mood', 'calm')).toEqual({ Mood: ['calm'] });
    expect(toggleLabel({ Mood: ['calm'] }, 'Mood', 'tense')).toEqual({
      Mood: ['calm', 'tense'],
    });
  });

  it('toggles a value out and drops the empty set key', () => {
    expect(toggleLabel({ Mood: ['calm'] }, 'Mood', 'calm')).toEqual({});
    expect(toggleLabel({ Mood: ['calm', 'tense'] }, 'Mood', 'calm')).toEqual({
      Mood: ['tense'],
    });
  });

  it('does not mutate the input', () => {
    const input = { Rating: ['sfw'] };
    toggleLabel(input, 'Rating', 'nsfw');
    expect(input).toEqual({ Rating: ['sfw'] });
  });

  it('hasLabels reflects any active value', () => {
    expect(hasLabels({})).toBe(false);
    expect(hasLabels({ Mood: [] })).toBe(false);
    expect(hasLabels({ Mood: ['calm'] })).toBe(true);
  });

  it('selectLabel replaces within a single-select set (no OR-accrue)', () => {
    // From empty: select sets the lone value.
    expect(selectLabel({}, 'Rating', 'sfw')).toEqual({ Rating: ['sfw'] });
    // Selecting a different value REPLACES, never accrues to two.
    expect(selectLabel({ Rating: ['sfw'] }, 'Rating', 'nsfw')).toEqual({ Rating: ['nsfw'] });
    // Re-selecting the active value clears the set.
    expect(selectLabel({ Rating: ['sfw'] }, 'Rating', 'sfw')).toEqual({});
    // Other sets are untouched.
    expect(selectLabel({ Mood: ['calm'], Rating: ['sfw'] }, 'Rating', 'nsfw')).toEqual({
      Mood: ['calm'],
      Rating: ['nsfw'],
    });
  });

  it('selectLabel does not mutate the input', () => {
    const input = { Rating: ['sfw'] };
    selectLabel(input, 'Rating', 'nsfw');
    expect(input).toEqual({ Rating: ['sfw'] });
  });
});
