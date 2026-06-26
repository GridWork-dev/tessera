import { ChevronLeft, ChevronRight, ImageOff, TriangleAlert } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { ImageItem, SearchResultItem } from '../api/types';
import { useExclusions, useFlagImage, useImages, useSearch } from '../hooks/queries';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { labelsToParams } from '../lib/labelFilter';
import { tagKey, useWorkspace } from '../store/useWorkspace';
import * as s from '../styles/workspace.css';
import { CommandBar } from './CommandBar';
import { CommandPalette } from './CommandPalette';
import { FacetRail } from './FacetRail';
import { FilterChips } from './FilterChips';
import { Grid } from './Grid';
import { Inspector } from './Inspector';
import { Lightbox } from './Lightbox';

const PAGE_SIZE = 100;

/** Adapt a /api/search result row to the ImageItem shape the Grid renders.
 *  Search rows carry no filename/flag/processed state, so fill safe defaults —
 *  the grid only needs id/file_hash/dimensions/rating to lay out + render. */
function searchResultToItem(r: SearchResultItem): ImageItem {
  return {
    id: r.id,
    file_hash: r.file_hash,
    filename: `#${r.id}`,
    person: r.person,
    width: r.width ?? null,
    height: r.height ?? null,
    rating: r.rating,
    processed: true,
    flagged: false,
    flag_action: null,
    tags: r.tags,
  };
}

export function Browse() {
  const q = useWorkspace((st) => st.q);
  const searchMode = useWorkspace((st) => st.searchMode);
  const person = useWorkspace((st) => st.person);
  const rating = useWorkspace((st) => st.rating);
  const activeTags = useWorkspace((st) => st.activeTags);
  const labels = useWorkspace((st) => st.labels);
  const processedFilter = useWorkspace((st) => st.processedFilter);
  const sort = useWorkspace((st) => st.sort);
  const activeCollectionId = useWorkspace((st) => st.activeCollectionId);
  const toggleCommand = useWorkspace((st) => st.toggleCommand);
  const selectedId = useWorkspace((st) => st.selectedId);
  const select = useWorkspace((st) => st.select);
  const inspectorOpen = useWorkspace((st) => st.inspectorOpen);
  const density = useWorkspace((st) => st.density);
  const lightboxId = useWorkspace((st) => st.lightboxId);
  const selectedIds = useWorkspace((st) => st.selectedIds);
  const toggleSelected = useWorkspace((st) => st.toggleSelected);
  const openLightbox = useWorkspace((st) => st.openLightbox);

  const { mutate: flagMutate } = useFlagImage();
  const [page, setPage] = useState(1);

  // Below 1024px the docked inspector is hidden (workspace.css), so a tile tap
  // has no detail/triage surface. Route it to the lightbox, which carries the
  // same keep/maybe/reject controls. Above it, tap selects (inspector shows).
  const compact = useMediaQuery('(max-width: 1024px)');

  // Exclusion rules hide images only when the backend gets exclude=true; flip it
  // on whenever any rule is enabled so the rail's Exclusions toggles actually
  // filter the grid (otherwise the toggle is a no-op that falsely claims to hide).
  const { data: exclusionsData } = useExclusions();
  const excludeActive = exclusionsData
    ? Object.values(exclusionsData.rules)
        .flat()
        .some((r) => r.enabled)
    : false;

  // 'tagged' => processed true, 'untagged' => false, 'all' => no filter.
  const processed =
    processedFilter === 'tagged' ? true : processedFilter === 'untagged' ? false : null;

  // Reset to page 1 + clear selection whenever the filter changes. The filter
  // fields are intentional triggers (not read in the body), so the exhaustive-
  // deps autofix (which would strip them and break this) is suppressed.
  // biome-ignore lint/correctness/useExhaustiveDependencies: filter fields are deliberate change triggers
  useEffect(() => {
    setPage(1);
    select(null);
  }, [
    q,
    searchMode,
    person,
    rating,
    activeTags,
    labels,
    processedFilter,
    sort,
    activeCollectionId,
    select,
  ]);

  // ⌘K / Ctrl-K opens the command palette (works even from inputs).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        toggleCommand();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [toggleCommand]);

  // Caption / Semantic hit /api/search; Tags uses the legacy facet query. Search
  // activates only with a query (an empty caption/semantic search is meaningless).
  const searchActive = searchMode !== 'tags' && q.trim() !== '';

  const labelParams = labelsToParams(labels);

  const imagesQuery = useImages({
    q: q || null,
    person,
    rating,
    tags: activeTags.map(tagKey),
    labels: labelParams,
    processed,
    collectionId: activeCollectionId,
    exclude: excludeActive,
    sort,
    page,
    // While a caption/semantic search is active the grid renders search
    // results, so the 100 image rows from this listing are discarded — but the
    // facet rail still consumes its (filter-wide, page-independent) label
    // facets. Fetch a single row instead of 100 to keep the rail without the
    // wasteful payload on every keystroke.
    limit: searchActive ? 1 : PAGE_SIZE,
  });

  const searchQuery = useSearch(
    {
      q: q || null,
      mode: searchMode === 'caption' ? 'caption' : 'semantic',
      tags: activeTags.map(tagKey),
      labels: labelParams,
      rating,
      person,
      page,
      page_size: PAGE_SIZE,
    },
    searchActive,
  );

  const { isLoading, isError } = searchActive ? searchQuery : imagesQuery;

  const searchItems = useMemo(
    () => (searchQuery.data?.results ?? []).map(searchResultToItem),
    [searchQuery.data],
  );

  const images = searchActive ? searchItems : (imagesQuery.data?.images ?? []);
  const total = searchActive ? searchQuery.data?.total : imagesQuery.data?.total;
  const totalPages = searchActive
    ? Math.max(1, Math.ceil((searchQuery.data?.total ?? 0) / PAGE_SIZE))
    : (imagesQuery.data?.total_pages ?? 1);

  // Backend degraded the requested mode (e.g. semantic gate off → tag matches).
  // Surface a subtle inline hint, mirroring the Inspector "Embeddings pending".
  const degradedFrom = searchActive ? searchQuery.data?.degraded_from : undefined;

  // Global keyboard layer: Escape clears selection; k/m/r triage the selected
  // asset; [ / ] page. Suppressed inside inputs and while the lightbox is open
  // (the Lightbox owns the keyboard then, incl. arrows for navigation).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target;
      if (
        t instanceof HTMLElement &&
        (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
      ) {
        return;
      }
      if (lightboxId !== null) return;
      if (e.key === 'Escape') {
        if (selectedId !== null) {
          e.preventDefault();
          select(null);
        }
        return;
      }
      if (e.key === '[') {
        e.preventDefault();
        setPage((p) => Math.max(1, p - 1));
        return;
      }
      if (e.key === ']') {
        e.preventDefault();
        setPage((p) => Math.min(totalPages, p + 1));
        return;
      }
      if (selectedId !== null && (e.key === 'k' || e.key === 'm' || e.key === 'r')) {
        e.preventDefault();
        const action = e.key === 'k' ? 'keep' : e.key === 'm' ? 'maybe' : 'reject';
        flagMutate({ id: selectedId, action });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [lightboxId, selectedId, select, flagMutate, totalPages]);

  return (
    <div className={s.appFrame} data-density={density}>
      <CommandBar total={total} loading={isLoading} />
      <div className={`${s.body}${inspectorOpen ? '' : ` ${s.bodyNoInspector}`}`}>
        <FacetRail labelFacets={imagesQuery.data?.label_facets} />

        <div className={s.gridRegion}>
          <FilterChips count={total} loading={isLoading} />
          {degradedFrom && (
            <div className={s.degradedHint} role="status">
              <span>
                {degradedFrom === 'semantic'
                  ? 'Semantic search pending — showing tag matches.'
                  : `${degradedFrom} search unavailable — showing tag matches.`}
              </span>
            </div>
          )}
          {isError ? (
            <div className={s.stateWrap}>
              <TriangleAlert size={28} aria-hidden="true" />
              <span className={s.stateTitle}>Couldn't load assets</span>
              <span className={s.stateHint}>
                The backend may be offline. Start it with <code>make backend</code> on :8000.
              </span>
            </div>
          ) : isLoading && images.length === 0 ? (
            <div className={s.stateWrap}>
              <span className={s.stateTitle}>Loading…</span>
            </div>
          ) : images.length === 0 ? (
            <div className={s.stateWrap}>
              <ImageOff size={28} aria-hidden="true" />
              <span className={s.stateTitle}>No matching assets</span>
              <span className={s.stateHint}>Adjust or clear the filters in the left rail.</span>
            </div>
          ) : (
            <>
              <Grid
                images={images}
                selectedId={selectedId}
                selectedIds={selectedIds}
                density={density}
                onSelect={(id) => {
                  select(id);
                  if (compact && id !== null) openLightbox(id);
                }}
                onActivate={openLightbox}
                onToggleSelect={toggleSelected}
              />
              {totalPages > 1 && (
                <div className={s.pager}>
                  <button
                    type="button"
                    className={s.pageBtn}
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    <ChevronLeft size={14} aria-hidden="true" />
                    Prev
                  </button>
                  <span className={s.pageInfo}>
                    Page {page} / {totalPages}
                  </span>
                  <button
                    type="button"
                    className={s.pageBtn}
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                    <ChevronRight size={14} aria-hidden="true" />
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        {inspectorOpen && <Inspector imageId={selectedId} onOpenSimilar={select} />}
      </div>

      <Lightbox images={images} />
      <CommandPalette />
    </div>
  );
}
