import { beforeEach, describe, expect, it } from 'vitest';
import { labelsToParams } from '../lib/labelFilter';
import { selectHasFilters, useWorkspace } from './useWorkspace';

// Task C: selecting a label facet value pushes label=<set>:<value> into the
// shared filter, OR-within / AND-across, and clears cleanly. Pure store logic.

describe('useWorkspace labels', () => {
  beforeEach(() => {
    useWorkspace.getState().clearFilters();
  });

  it('toggling a facet value sets the label filter (and the query params)', () => {
    useWorkspace.getState().toggleLabel('Rating', 'nsfw');
    expect(useWorkspace.getState().labels).toEqual({ Rating: ['nsfw'] });
    expect(labelsToParams(useWorkspace.getState().labels)).toEqual(['Rating:nsfw']);
    expect(selectHasFilters(useWorkspace.getState())).toBe(true);
  });

  it('OR within a set, AND across sets', () => {
    const { toggleLabel } = useWorkspace.getState();
    toggleLabel('Mood', 'calm');
    toggleLabel('Mood', 'tense');
    toggleLabel('Rating', 'sfw');
    expect(labelsToParams(useWorkspace.getState().labels)).toEqual([
      'Mood:calm',
      'Mood:tense',
      'Rating:sfw',
    ]);
  });

  it('toggling a value off removes it; clearing drops all labels', () => {
    const { toggleLabel } = useWorkspace.getState();
    toggleLabel('Rating', 'nsfw');
    toggleLabel('Rating', 'nsfw');
    expect(useWorkspace.getState().labels).toEqual({});
    toggleLabel('Mood', 'calm');
    useWorkspace.getState().clearLabels();
    expect(useWorkspace.getState().labels).toEqual({});
    expect(selectHasFilters(useWorkspace.getState())).toBe(false);
  });
});
