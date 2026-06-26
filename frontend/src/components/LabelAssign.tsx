import type { CSSProperties } from 'react';
import type { LabelSet } from '../api/types';
import { useAssignLabel, useImageLabels, useLabelSets, useUnassignLabel } from '../hooks/queries';
import { buildAssignedBySet } from '../lib/labelAssign';
import { labelChipStyle } from '../lib/labelColor';
import * as ws from '../styles/workspace.css';
import * as c from './LabelAssign.css';

/* ============================================================
   LabelAssign — renders every label set for the inspected image
   and lets the user assign/unassign values. Single-select sets
   replace (store-enforced); multi-select sets accumulate. Value
   colors come from label_definitions.color (DATA) via inline style.
   ============================================================ */

export function LabelAssign({ imageId }: { imageId: number }) {
  const sets = useLabelSets();
  const labels = useImageLabels(imageId);
  const assign = useAssignLabel(imageId);
  const unassign = useUnassignLabel(imageId);

  // NOTE: the Rating set is assigned by clicking its value chips below. It does
  // NOT bind a global k/m/r keyboard layer — those keys are the app-wide flag
  // triage (Browse + TrainingMode: keep/maybe/reject). A second window listener
  // here double-wrote (one keypress = flag AND rating); removed so k/m/r has a
  // single, unambiguous meaning on every screen.

  if (sets.isLoading || labels.isLoading) {
    return <span className={ws.stateHint}>Loading labels…</span>;
  }
  if (sets.isError || !sets.data || sets.data.length === 0) {
    return <span className={c.empty}>No label sets — create one in Settings.</span>;
  }

  // value -> assigned-row-id, keyed per set so we can toggle/replace.
  const assignedBySet = buildAssignedBySet(labels.data ?? []);

  const pending = assign.isPending || unassign.isPending;

  return (
    <div className={c.sets}>
      {sets.data.map((set) => (
        <SetBlock
          key={set.id}
          set={set}
          assigned={assignedBySet.get(set.id) ?? new Map()}
          disabled={pending}
          onToggle={(value, labelId) => {
            if (labelId !== undefined) {
              // Already assigned: clicking it removes it (both single + multi).
              unassign.mutate(labelId);
            } else {
              assign.mutate({ setId: set.id, value });
            }
          }}
        />
      ))}
    </div>
  );
}

function SetBlock({
  set,
  assigned,
  disabled,
  onToggle,
}: {
  set: LabelSet;
  assigned: Map<string, number>;
  disabled: boolean;
  onToggle: (value: string, labelId: number | undefined) => void;
}) {
  const single = set.single_select === 1;
  return (
    <div className={c.set}>
      <span className={c.setLabel}>
        {set.name}
        <span className={ws.chipConf}>{single ? 'one' : 'many'}</span>
      </span>
      {/* biome-ignore lint/a11y/useSemanticElements: a toolbar-style chip toggle group; role=group is the correct ARIA, not a fieldset */}
      <div className={c.valueWrap} role="group" aria-label={set.name}>
        {set.values.length === 0 ? (
          <span className={c.empty}>No values yet.</span>
        ) : (
          set.values.map((v) => {
            const labelId = assigned.get(v.value);
            const selected = labelId !== undefined;
            return (
              <ValueChip
                key={v.id}
                value={v.value}
                color={v.color}
                selected={selected}
                disabled={disabled}
                onClick={() => onToggle(v.value, labelId)}
              />
            );
          })
        )}
      </div>
    </div>
  );
}

/** One value chip — a toggle button (aria-pressed conveys selection). Single vs
 *  multi-select is enforced by the store (single replaces); the chip is the same
 *  affordance for both. Color is DATA (label_definitions.color), applied inline. */
function ValueChip({
  value,
  color,
  selected,
  disabled,
  onClick,
}: {
  value: string;
  color: string | null;
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  // Data color only when selected; unselected chips stay neutral chrome.
  const style: CSSProperties = selected ? labelChipStyle(color) : {};
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={`${c.chip}${selected ? ` ${c.chipSelected}` : ''}`}
      style={style}
      disabled={disabled}
      onClick={onClick}
    >
      {value}
    </button>
  );
}
