/**
 * Pure list-reorder for dnd-kit ``onDragEnd`` (Tasks D + E). Given the current
 * ordered id list and the active/over ids from a drag, return the new order.
 * Mirrors @dnd-kit/sortable's ``arrayMove`` but kept dependency-free + pure so
 * the reorder is unit-testable without the DOM/sensors. No-op when active===over
 * or either id is missing.
 */
export function reorderByIds<T extends string | number>(items: T[], active: T, over: T): T[] {
  if (active === over) return items;
  const from = items.indexOf(active);
  const to = items.indexOf(over);
  if (from === -1 || to === -1) return items;
  const next = [...items];
  const [moved] = next.splice(from, 1);
  if (moved === undefined) return items;
  next.splice(to, 0, moved);
  return next;
}
