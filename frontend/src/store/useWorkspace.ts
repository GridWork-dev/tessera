import { create } from 'zustand';
import { hasLabels, type LabelSelection, selectLabel, toggleLabel } from '../lib/labelFilter';

export interface ActiveTag {
  category: string;
  value: string;
}

export type SortKey =
  | 'recent'
  | 'created'
  | 'modified'
  | 'filename'
  | 'size'
  | 'random'
  | 'relevance';
/** Search surface: tags = /api/images facet query (default); caption/semantic =
 *  /api/search keyword/vector search. Caption & semantic activate only with a query. */
export type SearchModeUI = 'tags' | 'caption' | 'semantic';
/** Inspector detail level: basic = essentials; detailed = full power metadata. */
export type ViewDepth = 'basic' | 'detailed';
/** Density: comfortable = 38px rows / fewer cols; compact = 30px rows / more cols. */
export type Density = 'comfortable' | 'compact';
/** Tagged/untagged filter (maps to the /api/images `processed` param). */
export type ProcessedFilter = 'all' | 'tagged' | 'untagged';
/** Video sort keys — mirrors the backend VALID_VIDEO_SORTS. */
export type VideoSortKey = 'recent' | 'random' | 'filename' | 'size' | 'duration';

export const tagKey = (t: ActiveTag): string => `${t.category}:${t.value}`;

/** A persisted saved search/view — a named snapshot of the filter state. */
export interface SavedView {
  name: string;
  q: string;
  person: string | null;
  rating: string | null;
  activeTags: ActiveTag[];
  /** Generic label-set selections (Wave 2b): {setName: value[]} — AND across
   *  sets, OR within. Supersedes the fixed `rating` facet. */
  labels: LabelSelection;
  processedFilter: ProcessedFilter;
  sort: SortKey;
}

interface WorkspaceState {
  // ---- Filter ----
  q: string;
  searchMode: SearchModeUI;
  person: string | null;
  rating: string | null;
  activeTags: ActiveTag[]; // multi-facet AND
  labels: LabelSelection; // generic label-set facets (Wave 2b)
  processedFilter: ProcessedFilter;
  sort: SortKey;
  activeCollectionId: number | null; // collection filter (Browse-as-filter)

  // ---- Video-specific filter (Task F): shared store so Browse + Videos use one
  // filter model. person/rating/labels are the SHARED fields above. ----
  videoOrientation: string | null;
  videoDuration: string | null;
  videoHasAudio: boolean | null;
  videoSort: VideoSortKey;

  // ---- Command palette + saved views ----
  commandOpen: boolean;
  savedViews: SavedView[];

  // ---- Selection ----
  selectedId: number | null;
  selectedIds: Set<number>; // bulk triage

  // ---- UI mode ----
  inspectorOpen: boolean;
  lightboxId: number | null; // non-null => lightbox open on this image
  trainingMode: boolean;
  viewDepth: ViewDepth;
  density: Density;

  // ---- Actions: filter ----
  setQuery: (q: string) => void;
  setSearchMode: (mode: SearchModeUI) => void;
  setPerson: (person: string | null) => void;
  setRating: (rating: string | null) => void;
  toggleTag: (tag: ActiveTag) => void;
  removeTag: (tag: ActiveTag) => void;
  clearTags: () => void;
  toggleLabel: (set: string, value: string) => void;
  selectLabel: (set: string, value: string) => void;
  clearLabels: () => void;
  setProcessedFilter: (f: ProcessedFilter) => void;
  setSort: (sort: SortKey) => void;
  setActiveCollectionId: (id: number | null) => void;
  setVideoOrientation: (v: string | null) => void;
  setVideoDuration: (v: string | null) => void;
  setVideoHasAudio: (v: boolean | null) => void;
  setVideoSort: (sort: VideoSortKey) => void;
  clearVideoFilters: () => void;
  clearFilters: () => void;

  // ---- Actions: command palette + saved views ----
  setCommandOpen: (open: boolean) => void;
  toggleCommand: () => void;
  saveView: (name: string) => void;
  applyView: (view: SavedView) => void;
  deleteView: (name: string) => void;

  // ---- Actions: selection ----
  select: (id: number | null) => void;
  toggleSelected: (id: number, additive: boolean) => void;
  setSelected: (ids: number[]) => void;
  clearSelected: () => void;

  // ---- Actions: UI mode ----
  setInspectorOpen: (open: boolean) => void;
  openLightbox: (id: number) => void;
  closeLightbox: () => void;
  setTrainingMode: (on: boolean) => void;
  setViewDepth: (d: ViewDepth) => void;
  setDensity: (d: Density) => void;
  toggleDensity: () => void;
}

const hasTag = (tags: ActiveTag[], t: ActiveTag): boolean =>
  tags.some((x) => x.category === t.category && x.value === t.value);

// Persist the two view-preference knobs so a power user keeps their density /
// depth across sessions. Guarded for non-browser (SSR/headless) safety.
const LS = {
  density: 'mp.density',
  viewDepth: 'mp.viewDepth',
  savedViews: 'mp.savedViews',
} as const;
function lsGet<T extends string>(key: string, fallback: T, allowed: readonly T[]): T {
  if (typeof window === 'undefined') return fallback;
  const v = window.localStorage.getItem(key);
  return v && (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
}
function lsSet(key: string, val: string): void {
  if (typeof window !== 'undefined') window.localStorage.setItem(key, val);
}

const _SORTS: readonly SortKey[] = [
  'recent',
  'created',
  'modified',
  'filename',
  'size',
  'random',
  'relevance',
];
const _PROCESSED: readonly ProcessedFilter[] = ['all', 'tagged', 'untagged'];

/** Validate + normalize one parsed saved view; null if not usable. JSON.parse
 *  succeeding does NOT guarantee shape (user-mutable / legacy-schema localStorage),
 *  so a missing/garbage field must coerce to a safe default — never propagate
 *  `undefined` into `activeTags.map(...)` and white-screen Browse. */
function normalizeView(v: unknown): SavedView | null {
  if (!v || typeof v !== 'object') return null;
  const o = v as Record<string, unknown>;
  if (typeof o.name !== 'string' || o.name === '') return null;
  const activeTags = Array.isArray(o.activeTags)
    ? (o.activeTags as unknown[]).filter(
        (t): t is ActiveTag =>
          !!t &&
          typeof t === 'object' &&
          typeof (t as ActiveTag).category === 'string' &&
          typeof (t as ActiveTag).value === 'string',
      )
    : [];
  // labels: {setName: string[]} — coerce garbage to {} so a legacy/mutated blob
  // never propagates undefined into labelsToParams or the rail facet checks.
  const labels: LabelSelection = {};
  if (o.labels && typeof o.labels === 'object' && !Array.isArray(o.labels)) {
    for (const [set, vals] of Object.entries(o.labels as Record<string, unknown>)) {
      if (Array.isArray(vals)) {
        const clean = vals.filter((v): v is string => typeof v === 'string');
        if (clean.length > 0) labels[set] = clean;
      }
    }
  }
  return {
    name: o.name,
    q: typeof o.q === 'string' ? o.q : '',
    person: typeof o.person === 'string' ? o.person : null,
    rating: typeof o.rating === 'string' ? o.rating : null,
    activeTags,
    labels,
    processedFilter: _PROCESSED.includes(o.processedFilter as ProcessedFilter)
      ? (o.processedFilter as ProcessedFilter)
      : 'all',
    sort: _SORTS.includes(o.sort as SortKey) ? (o.sort as SortKey) : 'recent',
  };
}

function loadSavedViews(): SavedView[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(LS.savedViews);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(normalizeView).filter((v): v is SavedView => v !== null);
  } catch {
    return [];
  }
}
function persistSavedViews(views: SavedView[]): void {
  if (typeof window !== 'undefined')
    window.localStorage.setItem(LS.savedViews, JSON.stringify(views));
}

export const useWorkspace = create<WorkspaceState>((set, get) => ({
  q: '',
  searchMode: 'tags',
  person: null,
  rating: null,
  activeTags: [],
  labels: {},
  processedFilter: 'all',
  sort: 'recent',
  activeCollectionId: null,

  videoOrientation: null,
  videoDuration: null,
  videoHasAudio: null,
  videoSort: 'recent',

  commandOpen: false,
  savedViews: loadSavedViews(),

  selectedId: null,
  selectedIds: new Set<number>(),

  inspectorOpen: true,
  lightboxId: null,
  trainingMode: false,
  viewDepth: lsGet<ViewDepth>(LS.viewDepth, 'detailed', ['basic', 'detailed']),
  density: lsGet<Density>(LS.density, 'comfortable', ['comfortable', 'compact']),

  setQuery: (q) => set({ q }),
  setSearchMode: (searchMode) => set({ searchMode }),
  setPerson: (person) => set((s) => ({ person: s.person === person ? null : person })),
  setRating: (rating) => set((s) => ({ rating: s.rating === rating ? null : rating })),
  toggleTag: (tag) =>
    set((s) => ({
      activeTags: hasTag(s.activeTags, tag)
        ? s.activeTags.filter((x) => !(x.category === tag.category && x.value === tag.value))
        : [...s.activeTags, tag],
    })),
  removeTag: (tag) =>
    set((s) => ({
      activeTags: s.activeTags.filter(
        (x) => !(x.category === tag.category && x.value === tag.value),
      ),
    })),
  clearTags: () => set({ activeTags: [] }),
  toggleLabel: (setName, value) => set((s) => ({ labels: toggleLabel(s.labels, setName, value) })),
  selectLabel: (setName, value) => set((s) => ({ labels: selectLabel(s.labels, setName, value) })),
  clearLabels: () => set({ labels: {} }),
  setProcessedFilter: (processedFilter) => set({ processedFilter }),
  setSort: (sort) => set({ sort }),
  setActiveCollectionId: (activeCollectionId) => set({ activeCollectionId }),
  setVideoOrientation: (v) =>
    set((s) => ({ videoOrientation: s.videoOrientation === v ? null : v })),
  setVideoDuration: (v) => set((s) => ({ videoDuration: s.videoDuration === v ? null : v })),
  setVideoHasAudio: (v) => set((s) => ({ videoHasAudio: s.videoHasAudio === v ? null : v })),
  setVideoSort: (videoSort) => set({ videoSort }),
  clearVideoFilters: () =>
    set({
      person: null,
      rating: null,
      labels: {},
      videoOrientation: null,
      videoDuration: null,
      videoHasAudio: null,
    }),
  clearFilters: () =>
    set({
      q: '',
      searchMode: 'tags',
      person: null,
      rating: null,
      activeTags: [],
      labels: {},
      processedFilter: 'all',
      activeCollectionId: null,
      videoOrientation: null,
      videoDuration: null,
      videoHasAudio: null,
    }),

  setCommandOpen: (commandOpen) => set({ commandOpen }),
  toggleCommand: () => set((s) => ({ commandOpen: !s.commandOpen })),
  saveView: (name) =>
    set((s) => {
      const view: SavedView = {
        name,
        q: s.q,
        person: s.person,
        rating: s.rating,
        activeTags: s.activeTags,
        labels: s.labels,
        processedFilter: s.processedFilter,
        sort: s.sort,
      };
      const next = [...s.savedViews.filter((v) => v.name !== name), view];
      persistSavedViews(next);
      return { savedViews: next };
    }),
  applyView: (view) =>
    set({
      q: view.q ?? '',
      person: view.person ?? null,
      rating: view.rating ?? null,
      // Belt-and-suspenders: never assign undefined (Browse maps over activeTags).
      activeTags: Array.isArray(view.activeTags) ? view.activeTags : [],
      labels: view.labels ?? {},
      processedFilter: view.processedFilter ?? 'all',
      sort: view.sort ?? 'recent',
      activeCollectionId: null,
    }),
  deleteView: (name) =>
    set((s) => {
      const next = s.savedViews.filter((v) => v.name !== name);
      persistSavedViews(next);
      return { savedViews: next };
    }),

  select: (id) =>
    set((s) => ({ selectedId: id, inspectorOpen: id !== null ? true : s.inspectorOpen })),
  toggleSelected: (id, additive) =>
    set((s) => {
      const next = new Set(additive ? s.selectedIds : []);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { selectedIds: next };
    }),
  setSelected: (ids) => set({ selectedIds: new Set(ids) }),
  clearSelected: () => set({ selectedIds: new Set<number>() }),

  setInspectorOpen: (open) => set({ inspectorOpen: open }),
  openLightbox: (id) => set({ lightboxId: id, selectedId: id }),
  closeLightbox: () => set({ lightboxId: null }),
  setTrainingMode: (on) => set({ trainingMode: on }),
  setViewDepth: (d) => {
    lsSet(LS.viewDepth, d);
    set({ viewDepth: d });
  },
  setDensity: (d) => {
    lsSet(LS.density, d);
    set({ density: d });
  },
  toggleDensity: () => {
    const d: Density = get().density === 'comfortable' ? 'compact' : 'comfortable';
    lsSet(LS.density, d);
    set({ density: d });
  },
}));

/** Selector: is any filter currently narrowing the result set? */
export const selectHasFilters = (s: WorkspaceState): boolean =>
  s.q !== '' ||
  s.person !== null ||
  s.rating !== null ||
  s.activeTags.length > 0 ||
  hasLabels(s.labels) ||
  s.processedFilter !== 'all' ||
  s.activeCollectionId !== null;
