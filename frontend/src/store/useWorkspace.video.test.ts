import { beforeEach, describe, expect, it } from 'vitest';
import { useWorkspace } from './useWorkspace';

// Task F: Browse and Videos share ONE filter model. A label/person/rating filter
// set "in Browse" is the same store Videos reads, so it persists across the
// surface switch. Video-specific facets live alongside but are independent.

describe('shared filter store (Browse <-> Videos)', () => {
  beforeEach(() => {
    useWorkspace.getState().clearFilters();
  });

  it('a label filter set in Browse is visible to Videos (same store)', () => {
    // "In Browse" the user toggles a Rating label + a person.
    useWorkspace.getState().toggleLabel('Rating', 'nsfw');
    useWorkspace.getState().setPerson('Ana');
    // "Switching to Videos" reads the same shared fields — no reset.
    const st = useWorkspace.getState();
    expect(st.labels).toEqual({ Rating: ['nsfw'] });
    expect(st.person).toBe('Ana');
  });

  it('video-specific facets toggle independently of the shared fields', () => {
    const { setVideoOrientation, setVideoDuration, setVideoHasAudio } = useWorkspace.getState();
    setVideoOrientation('portrait');
    setVideoDuration('<30s');
    setVideoHasAudio(true);
    expect(useWorkspace.getState().videoOrientation).toBe('portrait');
    expect(useWorkspace.getState().videoDuration).toBe('<30s');
    expect(useWorkspace.getState().videoHasAudio).toBe(true);
    // toggling the same value again clears it.
    setVideoOrientation('portrait');
    expect(useWorkspace.getState().videoOrientation).toBeNull();
  });

  it('clearVideoFilters resets shared + video facets but not sort', () => {
    const st = useWorkspace.getState();
    st.toggleLabel('Mood', 'calm');
    st.setVideoOrientation('landscape');
    st.setVideoSort('duration');
    st.clearVideoFilters();
    const after = useWorkspace.getState();
    expect(after.labels).toEqual({});
    expect(after.videoOrientation).toBeNull();
    expect(after.videoSort).toBe('duration'); // sort is not a "filter"
  });
});
