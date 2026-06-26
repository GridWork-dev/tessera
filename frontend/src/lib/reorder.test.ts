import { describe, expect, it } from 'vitest';
import { reorderByIds } from './reorder';

describe('reorderByIds', () => {
  it('moves an item forward', () => {
    expect(reorderByIds(['a', 'b', 'c', 'd'], 'a', 'c')).toEqual(['b', 'c', 'a', 'd']);
  });

  it('moves an item backward', () => {
    expect(reorderByIds(['a', 'b', 'c', 'd'], 'd', 'b')).toEqual(['a', 'd', 'b', 'c']);
  });

  it('no-op when active === over', () => {
    expect(reorderByIds(['a', 'b'], 'a', 'a')).toEqual(['a', 'b']);
  });

  it('no-op when an id is missing', () => {
    expect(reorderByIds(['a', 'b'], 'x', 'a')).toEqual(['a', 'b']);
  });

  it('works on numeric ids', () => {
    expect(reorderByIds([1, 2, 3], 3, 1)).toEqual([3, 1, 2]);
  });

  it('does not mutate the input', () => {
    const input = ['a', 'b', 'c'];
    reorderByIds(input, 'a', 'c');
    expect(input).toEqual(['a', 'b', 'c']);
  });
});
