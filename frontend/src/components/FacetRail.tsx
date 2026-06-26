import { ChevronRight } from 'lucide-react';
import { Collapsible } from 'radix-ui';
import type { ReactNode } from 'react';
import { useState } from 'react';
import type { FacetValue, LabelFacets, LabelSet } from '../api/types';
import {
  useCollections,
  useExclusions,
  useFacets,
  useLabelSets,
  useToggleExclusion,
} from '../hooks/queries';
import { labelChipStyle } from '../lib/labelColor';
import type { ProcessedFilter } from '../store/useWorkspace';
import { selectHasFilters, tagKey, useWorkspace } from '../store/useWorkspace';
import * as ws from '../styles/workspace.css';
import * as c from './FacetRail.css';

// Tag categories surfaced as their own collapsible sections, in display order.
// 'person' and 'rating' get dedicated sections, so they're excluded here.
// `open` is the DEFAULT expanded state — high-traffic categories start open;
// long-tail ones (pose/composition/setting/location/lighting/mood/tags)
// collapse so the rail stays scannable.
const CATEGORY_SECTIONS: { key: string; open: boolean }[] = [
  { key: 'content_type', open: true },
  { key: 'clothing', open: true },
  { key: 'pose', open: false },
  { key: 'composition', open: false },
  { key: 'setting', open: false },
  { key: 'location', open: false },
  { key: 'lighting', open: false },
  { key: 'mood', open: false },
  { key: 'tags', open: false },
];

const PROCESSED_OPTIONS: { value: ProcessedFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'tagged', label: 'Tagged' },
  { value: 'untagged', label: 'Untagged' },
];

const TOP_PER_CATEGORY = 14;
const TOP_PEOPLE = 16;

const fmt = (n: number) => n.toLocaleString();
const humanize = (s: string) => s.replace(/_/g, ' ');

/** A collapsible group: button trigger (chevron + label + count) over a value list. */
function Section({
  label,
  count,
  defaultOpen,
  children,
}: {
  label: string;
  count: number;
  defaultOpen: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible.Root className={c.collapsible} open={open} onOpenChange={setOpen}>
      <Collapsible.Trigger className={c.trigger}>
        <ChevronRight size={14} className={c.chevron} aria-hidden />
        <span className={c.triggerLabel}>{label}</span>
        <span className={c.triggerCount}>{fmt(count)}</span>
      </Collapsible.Trigger>
      <Collapsible.Content className={c.content}>
        <div className={c.valueList}>{children}</div>
      </Collapsible.Content>
    </Collapsible.Root>
  );
}

/** One label set rendered as a collapsible facet group. Single-select sets read
 *  as a radio row (selecting replaces any other value in the set); multi-select
 *  sets read as a multi-toggle chip list (OR-within). The affordance (radio vs
 *  pressed button) and the action are both driven off `set.single_select`.
 *  Value color is DATA (inline), the count comes from disjunctive label_facets. */
function LabelSetSection({
  set,
  selected,
  counts,
  onToggle,
  onSelect,
}: {
  set: LabelSet;
  selected: string[];
  counts: Record<string, number> | undefined;
  onToggle: (value: string) => void;
  onSelect: (value: string) => void;
}) {
  if (set.values.length === 0) return null;
  const selectedSet = new Set(selected);
  const single = set.single_select === 1;
  // Single-select replaces in place (radio); multi accrues (OR-within, toggle).
  const rows = set.values.map((v) => {
    const on = selectedSet.has(v.value);
    const count = counts?.[v.value];
    const a11y = single
      ? ({ role: 'radio', 'aria-checked': on } as const)
      : ({ 'aria-pressed': on } as const);
    return (
      <button
        key={v.id}
        type="button"
        className={`${ws.facetRow}${on ? ` ${ws.facetRowActive}` : ''}`}
        onClick={single ? () => onSelect(v.value) : () => onToggle(v.value)}
        {...a11y}
      >
        <span className={ws.facetName}>
          <span className={c.labelDot} style={labelChipStyle(v.color)} aria-hidden />
          {humanize(v.value)}
        </span>
        {count !== undefined && <span className={ws.facetCount}>{fmt(count)}</span>}
      </button>
    );
  });
  return (
    <Section label={set.name} count={set.values.length} defaultOpen>
      {single ? (
        <div role="radiogroup" aria-label={set.name}>
          {rows}
        </div>
      ) : (
        rows
      )}
    </Section>
  );
}

export function FacetRail({ labelFacets }: { labelFacets?: LabelFacets | undefined }) {
  const { data, isLoading, isError } = useFacets();
  const labelSets = useLabelSets();
  const person = useWorkspace((st) => st.person);
  const activeTags = useWorkspace((st) => st.activeTags);
  const labels = useWorkspace((st) => st.labels);
  const processedFilter = useWorkspace((st) => st.processedFilter);
  const setPerson = useWorkspace((st) => st.setPerson);
  const toggleTag = useWorkspace((st) => st.toggleTag);
  const toggleLabel = useWorkspace((st) => st.toggleLabel);
  const selectLabel = useWorkspace((st) => st.selectLabel);
  const setProcessedFilter = useWorkspace((st) => st.setProcessedFilter);
  const clearFilters = useWorkspace((st) => st.clearFilters);
  const hasFilters = useWorkspace(selectHasFilters);
  const activeCollectionId = useWorkspace((st) => st.activeCollectionId);
  const setActiveCollectionId = useWorkspace((st) => st.setActiveCollectionId);

  const { data: collectionsData } = useCollections();
  const collections = collectionsData?.collections ?? [];
  const { data: exclusionsData } = useExclusions();
  const exclusions = exclusionsData ? Object.values(exclusionsData.rules).flat() : [];
  const toggleExclusion = useToggleExclusion();

  // O(1) membership for the active-marker check across all rendered rows.
  const activeKeys = new Set(activeTags.map(tagKey));

  const people = data
    ? Object.entries(data.people)
        .sort((a, b) => b[1] - a[1])
        .slice(0, TOP_PEOPLE)
    : [];

  const sets = labelSets.data ?? [];

  return (
    <nav className={ws.rail} aria-label="Filters">
      <div className={ws.railHeader}>
        <span className={ws.railHeaderTitle}>Filters</span>
        {hasFilters && (
          <button type="button" className={ws.clearBtn} onClick={clearFilters}>
            Clear all filters
          </button>
        )}
      </div>

      {/* Processing status — all / tagged / untagged */}
      <fieldset className={c.segmentWrap}>
        <legend className={c.srOnly}>Filter by processing status</legend>
        {PROCESSED_OPTIONS.map((opt) => {
          const on = processedFilter === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              className={`${c.segment}${on ? ` ${c.segmentActive}` : ''}`}
              onClick={() => setProcessedFilter(opt.value)}
              aria-pressed={on}
            >
              {opt.label}
            </button>
          );
        })}
      </fieldset>

      {isLoading && <div className={ws.sectionLabel}>Loading facets…</div>}
      {isError && <div className={ws.sectionLabel}>Couldn't load facets</div>}

      {/* Label sets (Wave 2b) — generic facets from /api/label-sets. Each value's
          color is DATA (label_definitions.color) applied inline; counts come from
          the listing response's disjunctive label_facets. Replaces the fixed
          Rating facet (Rating is now just a seeded single-select set). */}
      {sets.map((set) => (
        <LabelSetSection
          key={set.id}
          set={set}
          selected={labels[set.name] ?? []}
          counts={labelFacets?.[set.name]}
          onToggle={(value) => toggleLabel(set.name, value)}
          onSelect={(value) => selectLabel(set.name, value)}
        />
      ))}

      {/* People — single-select toggle */}
      {people.length > 0 && (
        <Section label="People" count={people.length} defaultOpen>
          {people.map(([name, count]) => {
            const on = person === name;
            return (
              <button
                key={name}
                type="button"
                className={`${ws.facetRow}${on ? ` ${ws.facetRowActive}` : ''}`}
                onClick={() => setPerson(name)}
                aria-pressed={on}
              >
                <span className={ws.facetName}>{humanize(name)}</span>
                <span className={ws.facetCount}>{fmt(count)}</span>
              </button>
            );
          })}
        </Section>
      )}

      {/* Tag categories — collapsible, multi-select (AND across categories) */}
      {data &&
        CATEGORY_SECTIONS.map(({ key, open }) => {
          const values: FacetValue[] | undefined = data.tags_by_category[key];
          if (!values || values.length === 0) return null;
          const top = [...values].sort((a, b) => b.count - a.count).slice(0, TOP_PER_CATEGORY);
          return (
            <Section key={key} label={humanize(key)} count={values.length} defaultOpen={open}>
              {top.map((v) => {
                const on = activeKeys.has(`${key}:${v.value}`);
                return (
                  <button
                    key={v.value}
                    type="button"
                    className={`${ws.facetRow}${on ? ` ${ws.facetRowActive}` : ''}`}
                    onClick={() => toggleTag({ category: key, value: v.value })}
                    aria-pressed={on}
                  >
                    <span className={ws.facetName}>{v.value}</span>
                    <span className={ws.facetCount}>{fmt(v.count)}</span>
                  </button>
                );
              })}
            </Section>
          );
        })}

      {/* Collections — collapsed; clicking one filters Browse to its members */}
      {collections.length > 0 && (
        <Section label="Collections" count={collections.length} defaultOpen={false}>
          {collections.map((col) => {
            const on = activeCollectionId === col.id;
            return (
              <button
                key={col.id}
                type="button"
                className={`${ws.facetRow}${on ? ` ${ws.facetRowActive}` : ''}`}
                onClick={() => setActiveCollectionId(on ? null : col.id)}
                aria-pressed={on}
              >
                <span className={ws.facetName}>{col.name}</span>
                <span className={ws.facetCount}>{fmt(col.image_count)}</span>
              </button>
            );
          })}
        </Section>
      )}

      {/* Exclusions — collapsed; row toggles a rule's enabled state (hides matches) */}
      {exclusions.length > 0 && (
        <Section label="Exclusions" count={exclusions.length} defaultOpen={false}>
          {exclusions.map((rule) => (
            <button
              key={rule.id}
              type="button"
              className={`${ws.facetRow}${rule.enabled ? ` ${ws.facetRowActive}` : ''}`}
              onClick={() => toggleExclusion.mutate({ ruleId: rule.id, enabled: !rule.enabled })}
              aria-pressed={rule.enabled}
              title={rule.enabled ? 'Enabled — hiding matches' : 'Disabled'}
            >
              <span className={ws.facetName}>
                {humanize(rule.category)}: {rule.value}
              </span>
              <span className={ws.facetCount}>{fmt(rule.match_count)}</span>
            </button>
          ))}
        </Section>
      )}
    </nav>
  );
}
