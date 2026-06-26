import {
  BookOpen,
  ChevronDown,
  LayoutPanelLeft,
  ListFilter,
  PanelRight,
  Rows3,
  Search,
  SlidersHorizontal,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { openDocs } from '../lib/docs';
import { type SearchModeUI, type SortKey, useWorkspace } from '../store/useWorkspace';
import * as ws from '../styles/workspace.css';
import { AppNav } from './AppNav';
import * as css from './CommandBar.css';

interface CommandBarProps {
  /** Total assets in the current result set (from Browse's image query). */
  total?: number | undefined;
  /** True while that result set is loading (shows a placeholder figure). */
  loading?: boolean;
}

const SORTS: ReadonlyArray<{ value: SortKey; label: string }> = [
  { value: 'recent', label: 'Recent' },
  { value: 'created', label: 'Date created' },
  { value: 'modified', label: 'Date modified' },
  { value: 'filename', label: 'Filename' },
  { value: 'size', label: 'File size' },
  { value: 'random', label: 'Random' },
  { value: 'relevance', label: 'Relevance' },
];

const SEARCH_MODES: ReadonlyArray<{ value: SearchModeUI; label: string }> = [
  { value: 'tags', label: 'Tags' },
  { value: 'caption', label: 'Caption' },
  { value: 'semantic', label: 'Semantic' },
];

const PLACEHOLDER: Record<SearchModeUI, string> = {
  tags: 'Search tags, people…',
  caption: 'Search captions…',
  semantic: 'Describe what you want…',
};

export function CommandBar({ total, loading = false }: CommandBarProps) {
  const q = useWorkspace((st) => st.q);
  const setQuery = useWorkspace((st) => st.setQuery);
  const searchMode = useWorkspace((st) => st.searchMode);
  const setSearchMode = useWorkspace((st) => st.setSearchMode);
  const sort = useWorkspace((st) => st.sort);
  const setSort = useWorkspace((st) => st.setSort);
  const density = useWorkspace((st) => st.density);
  const setDensity = useWorkspace((st) => st.setDensity);
  const viewDepth = useWorkspace((st) => st.viewDepth);
  const setViewDepth = useWorkspace((st) => st.setViewDepth);
  const inspectorOpen = useWorkspace((st) => st.inspectorOpen);
  const setInspectorOpen = useWorkspace((st) => st.setInspectorOpen);

  const inputRef = useRef<HTMLInputElement>(null);
  const [local, setLocal] = useState(q);

  // Debounce input → store (keeps the query key stable between keystrokes).
  useEffect(() => {
    const t = setTimeout(() => setQuery(local), 200);
    return () => clearTimeout(t);
  }, [local, setQuery]);

  // Keep the local field in sync when the store query changes externally — both
  // "Clear filters" (q='') AND applying a saved view (q=non-empty). Skip while the
  // input is focused so it never clobbers in-progress typing (the debounce owns
  // that direction). Without the non-empty case, applyView's query was invisible
  // and the debounce would then revert it on the next keystroke.
  useEffect(() => {
    if (document.activeElement !== inputRef.current) setLocal(q);
  }, [q]);

  // "/" focuses search from anywhere (when not already typing). ⌘K is owned by
  // the command palette (Browse), so search uses a distinct, non-conflicting key.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target;
      const typing =
        t instanceof HTMLElement &&
        (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
      if (e.key === '/' && !typing) {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Escape clears the field (and the store query). If already empty, blur out.
  const onSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      if (local === '') {
        inputRef.current?.blur();
      } else {
        setLocal('');
        setQuery('');
      }
    }
  };

  const compact = density === 'compact';
  const detailed = viewDepth === 'detailed';
  const figureLoading = loading && total === undefined;

  return (
    <header className={ws.commandBar}>
      {/* Shared brand wordmark + primary route nav (identical across pages). */}
      <AppNav />

      {/* Search */}
      <div className={css.searchWrap}>
        <Search size={15} className={css.searchIcon} aria-hidden="true" />
        <input
          ref={inputRef}
          className={css.searchInput}
          type="search"
          placeholder={PLACEHOLDER[searchMode]}
          value={local}
          onChange={(e) => setLocal(e.target.value)}
          onKeyDown={onSearchKeyDown}
          aria-label="Search assets"
          autoComplete="off"
          spellCheck={false}
        />
        <span
          className={`${css.kbdHint}${local ? ` ${css.kbdHintHidden}` : ''}`}
          aria-hidden="true"
        >
          <kbd className={css.kbd}>/</kbd>
        </span>
      </div>

      {/* Search mode — Tags (facet query) ⇄ Caption / Semantic (/api/search). */}
      {/* biome-ignore lint/a11y/useSemanticElements: a toolbar button group; role=group is the correct ARIA, not a fieldset */}
      <div className={css.modeSegment} role="group" aria-label="Search mode">
        {SEARCH_MODES.map(({ value, label }) => {
          const on = searchMode === value;
          return (
            <button
              key={value}
              type="button"
              className={`${css.modeSegmentBtn}${on ? ` ${css.modeSegmentBtnActive}` : ''}`}
              onClick={() => setSearchMode(value)}
              aria-pressed={on}
            >
              {label}
            </button>
          );
        })}
      </div>

      <div className={css.spacer} />

      {/* Right cluster */}
      <div className={css.rightCluster}>
        {/* Sort */}
        <div className={css.sortWrap}>
          <ListFilter size={14} className={css.sortIcon} aria-hidden="true" />
          <select
            className={css.sortSelect}
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            aria-label="Sort order"
          >
            {SORTS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <ChevronDown size={14} className={css.sortCaret} aria-hidden="true" />
        </div>

        <div className={css.divider} aria-hidden="true" />

        {/* Density segmented control */}
        {/* biome-ignore lint/a11y/useSemanticElements: a toolbar button group; role=group is the correct ARIA, not a fieldset */}
        <div className={css.segment} role="group" aria-label="Grid density">
          <button
            type="button"
            className={`${css.segmentBtn}${compact ? ` ${css.segmentBtnActive}` : ''}`}
            onClick={() => setDensity('compact')}
            aria-pressed={compact}
            title="Compact density"
          >
            <Rows3 size={15} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={`${css.segmentBtn}${!compact ? ` ${css.segmentBtnActive}` : ''}`}
            onClick={() => setDensity('comfortable')}
            aria-pressed={!compact}
            title="Comfortable density"
          >
            <LayoutPanelLeft size={15} aria-hidden="true" />
          </button>
        </div>

        {/* View-depth toggle — basic ⇄ detailed inspector metadata. */}
        <button
          type="button"
          className={`${css.iconButton}${detailed ? ` ${css.iconButtonActive}` : ''}`}
          onClick={() => setViewDepth(detailed ? 'basic' : 'detailed')}
          aria-pressed={detailed}
          title={detailed ? 'Detailed metadata (on)' : 'Show detailed metadata'}
        >
          <SlidersHorizontal size={16} aria-hidden="true" />
        </button>

        {/* Inspector toggle */}
        <button
          type="button"
          className={`${css.iconButton}${inspectorOpen ? ` ${css.iconButtonActive}` : ''}`}
          onClick={() => setInspectorOpen(!inspectorOpen)}
          aria-pressed={inspectorOpen}
          title={inspectorOpen ? 'Hide inspector' : 'Show inspector'}
        >
          <PanelRight size={16} aria-hidden="true" />
        </button>

        {/* Documentation — opens the hosted docs in the system browser. */}
        <button
          type="button"
          className={css.iconButton}
          onClick={() => void openDocs()}
          aria-label="Documentation"
          title="Documentation"
        >
          <BookOpen size={16} aria-hidden="true" />
        </button>

        <div className={css.divider} aria-hidden="true" />

        {/* Quiet asset figure — inline mono, fore2; not a hero metric. */}
        <div className={css.figure} aria-live="polite">
          {figureLoading ? (
            <span className={css.figureCount}>—</span>
          ) : (
            <>
              <span className={css.figureCount}>{(total ?? 0).toLocaleString()}</span>
              <span className={css.figureUnit}>assets</span>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
