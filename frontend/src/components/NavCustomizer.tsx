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
import { Eye, EyeOff, GripVertical } from 'lucide-react';
import type { HTMLAttributes } from 'react';
import type { Capabilities } from '../api/capabilities';
import type { NavPrefs, UiPrefs } from '../api/uiPrefs';
import { useCapabilities, useUiPrefs, useUpdateUiPrefs } from '../hooks/queries';
import { reorderByIds } from '../lib/reorder';
import { dashboardModules, MODULES, type ModuleDef, navModules } from '../modules/registry';
import * as c from './NavCustomizer.css';

type Surface = 'nav' | 'dashboard';

/** Is a module gated OFF by the server? (its gate capability is explicitly false). */
function isGatedOff(m: ModuleDef, caps: Capabilities | undefined): boolean {
  return !!m.gate && caps?.[m.gate] === false;
}

/** Build the next UiPrefs blob with one surface's nav prefs replaced. */
function withSurfacePrefs(prefs: UiPrefs | undefined, surface: Surface, nav: NavPrefs): UiPrefs {
  const base: UiPrefs = prefs ?? { version: 1, ui: {} };
  return { ...base, ui: { ...base.ui, [surface]: nav } };
}

/* ============================================================
   NavCustomizer — Settings control to reorder + hide modules for
   a surface (nav or dashboard). Two axes: a server-gated-off
   module is shown disabled/"unavailable" and is never user-
   toggleable (per spec); user order/hidden persist to /api/ui-prefs.
   ============================================================ */

export function NavCustomizer({ surface }: { surface: Surface }) {
  const caps = useCapabilities();
  const prefs = useUiPrefs();
  const update = useUpdateUiPrefs();
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const navPrefs = prefs.data?.ui[surface];
  // All modules for this surface (registry order), including gated-off so they
  // can be shown as unavailable. Visible (ordered) ones come from the resolver.
  const all = MODULES.filter((m) =>
    surface === 'nav' ? m.surface === 'nav' || m.surface === 'both' : m.surface !== 'nav',
  );
  const visible =
    surface === 'nav' ? navModules(navPrefs, caps.data) : dashboardModules(navPrefs, caps.data);
  const visibleIds = visible.map((m) => m.id);

  // Gated-off modules: shown after the visible list, disabled.
  const gatedOff = all.filter((m) => isGatedOff(m, caps.data));
  // User-hidden (but available) modules: shown so the user can re-enable them.
  const hidden = new Set(navPrefs?.hidden ?? []);
  const hiddenAvailable = all.filter((m) => hidden.has(m.id) && !isGatedOff(m, caps.data));

  function persist(next: NavPrefs) {
    update.mutate(withSurfacePrefs(prefs.data, surface, next));
  }

  function onDragEnd(e: DragEndEvent) {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const nextOrder = reorderByIds(visibleIds, String(active.id), String(over.id));
    persist({ order: nextOrder, hidden: [...hidden] });
  }

  function setHidden(id: string, hide: boolean) {
    const nextHidden = new Set(hidden);
    if (hide) nextHidden.add(id);
    else nextHidden.delete(id);
    // Preserve the current visible order; re-show appends at its registry slot.
    persist({ order: visibleIds, hidden: [...nextHidden] });
  }

  return (
    <div className={c.list}>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={visibleIds} strategy={verticalListSortingStrategy}>
          {visible.map((m) => (
            <SortableModuleRow key={m.id} module={m} onHide={() => setHidden(m.id, true)} />
          ))}
        </SortableContext>
      </DndContext>

      {hiddenAvailable.map((m) => (
        <ModuleRow
          key={m.id}
          module={m}
          hidden
          gated={false}
          gripProps={undefined}
          onToggle={() => setHidden(m.id, false)}
        />
      ))}

      {gatedOff.map((m) => (
        <ModuleRow key={m.id} module={m} hidden={false} gated gripProps={undefined} />
      ))}
    </div>
  );
}

function SortableModuleRow({ module, onHide }: { module: ModuleDef; onHide: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: module.id,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : undefined,
  };
  return (
    <div ref={setNodeRef} style={style}>
      <ModuleRow
        module={module}
        hidden={false}
        gated={false}
        gripProps={{ ...attributes, ...listeners }}
        onToggle={onHide}
      />
    </div>
  );
}

function ModuleRow({
  module,
  hidden,
  gated,
  gripProps,
  onToggle,
}: {
  module: ModuleDef;
  hidden: boolean;
  gated: boolean;
  gripProps: HTMLAttributes<HTMLSpanElement> | undefined;
  onToggle?: () => void;
}) {
  const Icon = module.icon;
  return (
    <div className={`${c.row}${gated ? ` ${c.rowGated}` : ''}`}>
      {gated || !gripProps ? (
        <span className={`${c.grip} ${c.gripDisabled}`} aria-hidden>
          <GripVertical size={13} />
        </span>
      ) : (
        // biome-ignore lint/a11y/useSemanticElements: dnd grip handle; the keyboard sensor needs listeners on this element, not a native button
        <span
          className={c.grip}
          role="button"
          tabIndex={0}
          aria-label={`Reorder ${module.label}`}
          {...gripProps}
        >
          <GripVertical size={13} />
        </span>
      )}
      <span className={c.icon}>
        <Icon size={15} />
      </span>
      <span className={c.label}>{module.label}</span>
      {gated ? (
        <span className={c.unavailable}>unavailable</span>
      ) : (
        <button
          type="button"
          className={`${c.toggle}${hidden ? ` ${c.toggleHidden}` : ''}`}
          aria-pressed={!hidden}
          onClick={onToggle}
        >
          {hidden ? <EyeOff size={13} aria-hidden /> : <Eye size={13} aria-hidden />}
          {hidden ? 'Hidden' : 'Shown'}
        </button>
      )}
    </div>
  );
}
