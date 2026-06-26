import { describe, expect, it } from 'vitest';
import { labelChipStyle, readableOn } from './labelColor';

describe('labelColor', () => {
  it('picks dark text on a light data color (AA contrast)', () => {
    expect(readableOn('#ffffff')).toBe('#000000');
  });

  it('picks light text on a dark data color (AA contrast)', () => {
    expect(readableOn('#101418')).toBe('#ffffff');
  });

  it('falls back to a neutral chip when color is null/empty', () => {
    const s = labelChipStyle(null);
    // No data color -> no inline background (chip uses the neutral surface token).
    expect(s.backgroundColor).toBeUndefined();
    expect(s.color).toBeUndefined();
  });

  it('produces a tinted bg + readable fg for a valid data color', () => {
    const s = labelChipStyle('#d27a7a');
    expect(s.backgroundColor).toBe('#d27a7a');
    expect(s.color).toBe(readableOn('#d27a7a'));
  });

  it('ignores malformed hex (no crash, neutral chip)', () => {
    const s = labelChipStyle('not-a-color');
    expect(s.backgroundColor).toBeUndefined();
  });
});
