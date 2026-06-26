/**
 * The shared filter model carries label-set selections as
 * ``Record<setName, value[]>`` (AND across sets, OR within a set — mirrors the
 * backend ``label=<set>:<value>`` semantics). These pure helpers convert to/from
 * the repeatable ``<set>:<value>`` query-param list and toggle a value. Pure so
 * Browse↔Videos share one model and the conversion is unit-testable.
 */

export type LabelSelection = Record<string, string[]>;

/** Flatten the selection to a sorted, stable ``<set>:<value>`` param list. */
export function labelsToParams(labels: LabelSelection): string[] {
  const out: string[] = [];
  for (const set of Object.keys(labels).sort()) {
    for (const value of [...(labels[set] ?? [])].sort()) {
      out.push(`${set}:${value}`);
    }
  }
  return out;
}

/** Toggle one value within a set (OR-within). Removing the last value drops the
 *  set key entirely so an empty selection is ``{}`` (clean for `hasFilters`). */
export function toggleLabel(labels: LabelSelection, set: string, value: string): LabelSelection {
  const current = labels[set] ?? [];
  const has = current.includes(value);
  const nextValues = has ? current.filter((v) => v !== value) : [...current, value];
  const next: LabelSelection = { ...labels };
  if (nextValues.length === 0) {
    delete next[set];
  } else {
    next[set] = nextValues;
  }
  return next;
}

/** Single-select within a set: selecting a value REPLACES any other value in
 *  that set; re-selecting the active value clears the set. Mirrors the server's
 *  DELETE+INSERT replace semantics for single_select sets. */
export function selectLabel(labels: LabelSelection, set: string, value: string): LabelSelection {
  const isActive = (labels[set] ?? []).includes(value);
  const next: LabelSelection = { ...labels };
  if (isActive) {
    delete next[set];
  } else {
    next[set] = [value];
  }
  return next;
}

/** True when any label value is selected. */
export function hasLabels(labels: LabelSelection): boolean {
  return Object.values(labels).some((vs) => vs.length > 0);
}
