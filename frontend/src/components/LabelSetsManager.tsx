import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, Plus, X } from 'lucide-react';
import { type FormEvent, type HTMLAttributes, useState } from 'react';
import type { LabelSet } from '../api/types';
import {
  useAddLabelValue,
  useCreateLabelSet,
  useDeleteLabelSet,
  useLabelSets,
  usePatchLabelSet,
  useRemoveLabelValue,
} from '../hooks/queries';
import { labelChipStyle } from '../lib/labelColor';
import { reorderByIds } from '../lib/reorder';
import * as c from './LabelSetsManager.css';

/* ============================================================
   LabelSetsManager — Settings panel to CRUD custom label sets:
   drag-reorder (dnd-kit, persisted via sort_order), rename,
   toggle single-select, delete (system sets confirm), and add/
   remove values with a per-value DATA color. Mounted in Settings.
   ============================================================ */

export function LabelSetsManager() {
  const sets = useLabelSets();
  const patch = usePatchLabelSet();
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  if (sets.isLoading) return <span className={c.hint}>Loading label sets…</span>;
  if (sets.isError) return <span className={c.hint}>Couldn't load label sets.</span>;

  const ordered = sets.data ?? [];
  const ids = ordered.map((s) => s.id);

  function onDragEnd(e: DragEndEvent) {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const next = reorderByIds(ids, Number(active.id), Number(over.id));
    // Persist the new sort_order for each set by index. One PATCH per set keeps
    // the route simple (no bulk endpoint); the list is short.
    next.forEach((setId, index) => {
      patch.mutate({ setId, body: { sort_order: index } });
    });
  }

  return (
    <div className={c.wrap}>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          <div className={c.list}>
            {ordered.map((set) => (
              <SortableSetRow key={set.id} set={set} />
            ))}
          </div>
        </SortableContext>
      </DndContext>
      <NewSetForm />
    </div>
  );
}

function SortableSetRow({ set }: { set: LabelSet }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: set.id,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : undefined,
  };
  return (
    <div ref={setNodeRef} style={style} className={c.setRow}>
      <SetRow set={set} gripProps={{ ...attributes, ...listeners }} />
    </div>
  );
}

function SetRow({ set, gripProps }: { set: LabelSet; gripProps: HTMLAttributes<HTMLSpanElement> }) {
  const patch = usePatchLabelSet();
  const del = useDeleteLabelSet();
  const addValue = useAddLabelValue();
  const removeValue = useRemoveLabelValue();
  const [name, setName] = useState(set.name);
  const [newValue, setNewValue] = useState('');
  const [newColor, setNewColor] = useState('#62b8dc');
  const single = set.single_select === 1;

  function commitName() {
    const v = name.trim();
    if (v && v !== set.name) patch.mutate({ setId: set.id, body: { name: v } });
  }

  function submitValue(e: FormEvent) {
    e.preventDefault();
    const v = newValue.trim();
    if (!v || addValue.isPending) return;
    addValue.mutate(
      { setId: set.id, value: v, color: newColor },
      { onSuccess: () => setNewValue('') },
    );
  }

  function deleteSet() {
    if (set.is_system === 1) {
      const ok = window.confirm(
        `"${set.name}" is a system set. Deleting it removes the set and all its assignments. Continue?`,
      );
      if (!ok) return;
    }
    del.mutate(set.id);
  }

  return (
    <>
      <div className={c.setHead}>
        {/* biome-ignore lint/a11y/useSemanticElements: dnd grip handle; the keyboard sensor needs the listeners on this element, not a native button */}
        <span
          className={c.grip}
          role="button"
          tabIndex={0}
          aria-label={`Reorder ${set.name}`}
          {...gripProps}
        >
          <GripVertical size={14} aria-hidden />
        </span>
        <input
          className={c.nameInput}
          value={name}
          aria-label={`Set name for ${set.name}`}
          onChange={(e) => setName(e.target.value)}
          onBlur={commitName}
        />
        {set.is_system === 1 && <span className={c.systemBadge}>system</span>}
        <button
          type="button"
          className={`${c.toggle}${single ? ` ${c.toggleOn}` : ''}`}
          aria-pressed={single}
          onClick={() => patch.mutate({ setId: set.id, body: { single_select: !single } })}
          title="Single-select: at most one value per asset"
        >
          {single ? 'Single' : 'Multi'}
        </button>
        <button
          type="button"
          className={c.iconBtn}
          aria-label={`Delete set ${set.name}`}
          onClick={deleteSet}
        >
          <X size={14} aria-hidden />
        </button>
      </div>

      <div className={c.valueWrap}>
        {set.values.length === 0 ? (
          <span className={c.hint}>No values yet.</span>
        ) : (
          set.values.map((v) => (
            <span className={c.valueChip} key={v.id}>
              <span className={c.valueDot} style={labelChipStyle(v.color)} aria-hidden />
              {v.value}
              <button
                type="button"
                className={c.removeBtn}
                aria-label={`Remove value ${v.value}`}
                onClick={() => removeValue.mutate({ setId: set.id, valueId: v.id })}
              >
                <X size={11} aria-hidden />
              </button>
            </span>
          ))
        )}
      </div>

      <form className={c.addRow} onSubmit={submitValue}>
        <input
          className={c.addInput}
          value={newValue}
          placeholder="Add a value…"
          aria-label={`Add a value to ${set.name}`}
          maxLength={60}
          onChange={(e) => setNewValue(e.target.value)}
        />
        <input
          type="color"
          className={c.colorInput}
          value={newColor}
          aria-label={`Color for the new value in ${set.name}`}
          onChange={(e) => setNewColor(e.target.value)}
        />
        <button type="submit" className={c.primaryBtn} disabled={newValue.trim() === ''}>
          <Plus size={13} aria-hidden />
          Add
        </button>
      </form>
    </>
  );
}

function NewSetForm() {
  const create = useCreateLabelSet();
  const [name, setName] = useState('');
  const [single, setSingle] = useState(false);

  function submit(e: FormEvent) {
    e.preventDefault();
    const v = name.trim();
    if (!v || create.isPending) return;
    create.mutate({ name: v, single_select: single }, { onSuccess: () => setName('') });
  }

  return (
    <form className={c.newSetRow} onSubmit={submit}>
      <input
        className={c.addInput}
        value={name}
        placeholder="New label set…"
        aria-label="New label set name"
        maxLength={40}
        onChange={(e) => setName(e.target.value)}
      />
      <button
        type="button"
        className={`${c.toggle}${single ? ` ${c.toggleOn}` : ''}`}
        aria-pressed={single}
        onClick={() => setSingle((s) => !s)}
      >
        {single ? 'Single' : 'Multi'}
      </button>
      <button type="submit" className={c.primaryBtn} disabled={name.trim() === ''}>
        <Plus size={13} aria-hidden />
        Create
      </button>
    </form>
  );
}
