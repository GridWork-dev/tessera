import { X } from 'lucide-react';
import { useCollections } from '../hooks/queries';
import { type ActiveTag, selectHasFilters, tagKey, useWorkspace } from '../store/useWorkspace';
import * as c from './FilterChips.css';
import { RatingChip } from './RatingChip';

interface FilterChipsProps {
  /** Total matching assets (from the images query); shown right-aligned in mono. */
  count?: number | undefined;
  /** A fetch is in flight — the count is stale, dim it rather than hide it. */
  loading?: boolean;
}

const PROCESSED_LABEL: Record<'tagged' | 'untagged', string> = {
  tagged: 'tagged',
  untagged: 'untagged',
};

export function FilterChips({ count, loading = false }: FilterChipsProps) {
  const q = useWorkspace((st) => st.q);
  const person = useWorkspace((st) => st.person);
  const rating = useWorkspace((st) => st.rating);
  const activeTags = useWorkspace((st) => st.activeTags);
  const labels = useWorkspace((st) => st.labels);
  const processedFilter = useWorkspace((st) => st.processedFilter);

  const setQuery = useWorkspace((st) => st.setQuery);
  const setPerson = useWorkspace((st) => st.setPerson);
  const setRating = useWorkspace((st) => st.setRating);
  const removeTag = useWorkspace((st) => st.removeTag);
  const toggleLabel = useWorkspace((st) => st.toggleLabel);
  const setProcessedFilter = useWorkspace((st) => st.setProcessedFilter);
  const activeCollectionId = useWorkspace((st) => st.activeCollectionId);
  const setActiveCollectionId = useWorkspace((st) => st.setActiveCollectionId);
  const clearFilters = useWorkspace((st) => st.clearFilters);

  const hasFilters = useWorkspace(selectHasFilters);

  const { data: collectionsData } = useCollections();
  const activeCollection =
    activeCollectionId !== null
      ? collectionsData?.collections.find((col) => col.id === activeCollectionId)
      : undefined;

  const countNode =
    count !== undefined ? (
      <span className={`${c.count}${loading ? ` ${c.countLoading}` : ''}`}>
        {count.toLocaleString()} {count === 1 ? 'asset' : 'assets'}
      </span>
    ) : null;

  // No active filters: render just the count row (or nothing if no count yet).
  if (!hasFilters) {
    if (countNode === null) return null;
    return (
      <div className={c.strip}>
        <div className={c.right}>{countNode}</div>
      </div>
    );
  }

  return (
    <div className={c.strip}>
      <div className={c.chips}>
        {q !== '' && (
          <span className={c.chip}>
            <span className={c.chipText}>
              <span className={c.chipKind}>search:</span> {q}
            </span>
            <RemoveButton label={`Clear search "${q}"`} onClick={() => setQuery('')} />
          </span>
        )}

        {person !== null && (
          <span className={c.chip}>
            <span className={c.chipText}>
              <span className={c.chipKind}>person:</span> {person}
            </span>
            <RemoveButton label={`Remove person ${person}`} onClick={() => setPerson(null)} />
          </span>
        )}

        {rating !== null && (
          <span className={`${c.chip} ${c.ratingChip}`}>
            <RatingChip rating={rating} />
            <RemoveButton label="Clear rating filter" onClick={() => setRating(null)} />
          </span>
        )}

        {activeTags.map((tag: ActiveTag) => (
          <span className={c.chip} key={tagKey(tag)}>
            <span className={c.chipText}>
              <span className={c.chipKind}>{tag.category}:</span> {tag.value}
            </span>
            <RemoveButton
              label={`Remove tag ${tag.category}: ${tag.value}`}
              onClick={() => removeTag(tag)}
            />
          </span>
        ))}

        {Object.entries(labels).flatMap(([set, values]) =>
          values.map((value) => (
            <span className={c.chip} key={`${set}:${value}`}>
              <span className={c.chipText}>
                <span className={c.chipKind}>{set.toLowerCase()}:</span> {value}
              </span>
              <RemoveButton
                label={`Remove label ${set}: ${value}`}
                onClick={() => toggleLabel(set, value)}
              />
            </span>
          )),
        )}

        {processedFilter !== 'all' && (
          <span className={c.chip}>
            <span className={c.chipText}>
              <span className={c.chipKind}>status:</span> {PROCESSED_LABEL[processedFilter]}
            </span>
            <RemoveButton label="Clear status filter" onClick={() => setProcessedFilter('all')} />
          </span>
        )}

        {activeCollectionId !== null && (
          <span className={c.chip}>
            <span className={c.chipText}>
              <span className={c.chipKind}>collection:</span>{' '}
              {activeCollection?.name ?? `#${activeCollectionId}`}
            </span>
            <RemoveButton
              label="Clear collection filter"
              onClick={() => setActiveCollectionId(null)}
            />
          </span>
        )}
      </div>

      <div className={c.right}>
        {countNode}
        <button type="button" className={c.clearAll} onClick={() => clearFilters()}>
          Clear all filters
        </button>
      </div>
    </div>
  );
}

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" className={c.remove} aria-label={label} onClick={onClick}>
      <X size={12} aria-hidden="true" />
    </button>
  );
}
