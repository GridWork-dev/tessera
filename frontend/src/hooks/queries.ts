import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getCapabilities } from '../api/capabilities';
import type { ImageFilter, SearchParams, VideoFilter } from '../api/endpoints';
import {
  addLabel,
  addToCollection,
  batchFlag,
  createCollection,
  createExclusion,
  deleteCollection,
  deleteLabel,
  fetchExclusionSuggestions,
  fetchPreferenceFeed,
  flagImage,
  getDirectoryStats,
  getFacets,
  getImageDetail,
  getLabels,
  getPipeline,
  getPreferenceStatus,
  getStats,
  getSystem,
  getThroughput,
  getVideoDetail,
  getVideoFacets,
  listCollections,
  listExclusions,
  listImages,
  listVideos,
  removeFromCollection,
  search,
  setRating,
  similar,
  toggleExclusion,
} from '../api/endpoints';
import type { CreateSetBody, PatchSetBody } from '../api/labels';
import {
  addLabelValue,
  assignLabel,
  createLabelSet,
  deleteLabelSet,
  getImageLabels,
  listLabelSets,
  patchLabelSet,
  removeLabelValue,
  unassignLabel,
} from '../api/labels';
import type { ImageLabel, ImagesResponse, LabelSet } from '../api/types';
import type { UiPrefs } from '../api/uiPrefs';
import { getUiPrefs, putUiPrefs } from '../api/uiPrefs';

type Rating = 'unrated' | 'sfw' | 'suggestive' | 'nsfw';

type FlagAction = 'reject' | 'maybe' | 'keep';

// Query keys — stable, serializable. See docs/specs/backend-search-api.md.
export const keys = {
  stats: ['stats'] as const,
  facets: ['facets'] as const,
  images: (filter: ImageFilter) => ['images', filter] as const,
  imageDetail: (id: number) => ['imageDetail', id] as const,
  similar: (id: number, tags: string[]) => ['similar', id, tags] as const,
  search: (params: SearchParams) => ['search', params] as const,
  pipeline: ['pipeline'] as const,
  system: ['system'] as const,
  throughput: (minutes: number) => ['throughput', minutes] as const,
  directories: ['directories'] as const,
  labels: (id: number) => ['labels', id] as const,
  collections: ['collections'] as const,
  collection: (id: number) => ['collection', id] as const,
  videos: (filter: VideoFilter) => ['videos', filter] as const,
  video: (id: number) => ['video', id] as const,
  videoFacets: ['videoFacets'] as const,
  exclusions: ['exclusions'] as const,
  preferenceStatus: ['preferenceStatus'] as const,
  labelSets: ['labelSets'] as const,
  imageLabels: (id: number) => ['imageLabels', id] as const,
  capabilities: ['capabilities'] as const,
  uiPrefs: ['uiPrefs'] as const,
};

// ---- Module registry inputs (Wave 2b): server gates + user prefs ----

/** Server capability gates (faces/geo/video/license). Long staleTime — gates
 *  change only on server config, not during a session. */
export function useCapabilities() {
  return useQuery({
    queryKey: keys.capabilities,
    queryFn: ({ signal }) => getCapabilities(signal),
    staleTime: 5 * 60_000,
  });
}

/** The UI-preferences blob (nav/dashboard order+hidden, theme). */
export function useUiPrefs() {
  return useQuery({
    queryKey: keys.uiPrefs,
    queryFn: ({ signal }) => getUiPrefs(signal),
    staleTime: 60_000,
  });
}

/** Whole-blob upsert of UI prefs, optimistic so reorder/hide feels instant. */
export function useUpdateUiPrefs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (prefs: UiPrefs) => putUiPrefs(prefs),
    onMutate: async (prefs) => {
      await qc.cancelQueries({ queryKey: keys.uiPrefs });
      const prev = qc.getQueryData<UiPrefs>(keys.uiPrefs);
      qc.setQueryData<UiPrefs>(keys.uiPrefs, prefs);
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.uiPrefs, ctx.prev);
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: keys.uiPrefs }),
  });
}

export function useStats() {
  return useQuery({
    queryKey: keys.stats,
    queryFn: ({ signal }) => getStats(signal),
    staleTime: 30_000,
  });
}

export function useFacets() {
  return useQuery({
    queryKey: keys.facets,
    queryFn: ({ signal }) => getFacets(signal),
    staleTime: 60_000,
  });
}

export function useImages(filter: ImageFilter) {
  return useQuery({
    queryKey: keys.images(filter),
    queryFn: ({ signal }) => listImages(filter, signal),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });
}

/** Full detail for the in-depth inspector + lightbox. Disabled until selected. */
export function useImageDetail(id: number | null) {
  return useQuery({
    queryKey: keys.imageDetail(id ?? -1),
    queryFn: ({ signal }) => getImageDetail(id as number, signal),
    enabled: id !== null,
    staleTime: 30_000,
  });
}

/**
 * Similar-by-id. Disabled until selected. Degrades gracefully: the backend
 * returns vectors_unavailable=true while Tier-1 embeddings are pending, so the
 * UI shows an explanatory empty state rather than erroring.
 *
 * `tags` (optional, "category:value") pre-filters neighbours to an allowlist —
 * drives "similar within the current filter". Omitted ⇒ unfiltered (default).
 */
export function useSimilar(id: number | null, tags: string[] = []) {
  return useQuery({
    queryKey: keys.similar(id ?? -1, tags),
    queryFn: ({ signal }) => similar(id as number, { k: 24, tags }, signal),
    enabled: id !== null,
    staleTime: 30_000,
    retry: false,
  });
}

/**
 * Hybrid/caption/semantic search over /api/search. Disabled until a query is
 * present. Degrades gracefully: the backend may return `degraded_from` (e.g.
 * semantic gate off → tag matches) or `vectors_unavailable`; callers surface a
 * hint rather than erroring.
 */
export function useSearch(params: SearchParams, enabled: boolean) {
  return useQuery({
    queryKey: keys.search(params),
    queryFn: ({ signal }) => search(params, signal),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
    retry: false,
  });
}

// ---- Monitoring (dashboard). Poll on an interval; cheap, read-only. ----

export function usePipeline(refetchMs = 5_000) {
  return useQuery({
    queryKey: keys.pipeline,
    queryFn: ({ signal }) => getPipeline(signal),
    refetchInterval: refetchMs,
    staleTime: 2_000,
  });
}

export function useSystem(refetchMs = 3_000) {
  return useQuery({
    queryKey: keys.system,
    queryFn: ({ signal }) => getSystem(signal),
    refetchInterval: refetchMs,
    staleTime: 1_000,
  });
}

export function useThroughput(minutes = 10, refetchMs = 15_000) {
  return useQuery({
    queryKey: keys.throughput(minutes),
    queryFn: ({ signal }) => getThroughput(minutes, signal),
    refetchInterval: refetchMs,
  });
}

export function useDirectoryStats() {
  return useQuery({
    queryKey: keys.directories,
    queryFn: ({ signal }) => getDirectoryStats(signal),
    staleTime: 60_000,
  });
}

export function useLabels(id: number | null) {
  return useQuery({
    queryKey: keys.labels(id ?? -1),
    queryFn: ({ signal }) => getLabels(id as number, signal),
    enabled: id !== null,
    staleTime: 30_000,
  });
}

// ---- Mutations ----

/** Patch every cached /api/images page in place so a flag reflects instantly. */
function patchImagesCache(
  qc: ReturnType<typeof useQueryClient>,
  id: number,
  patch: { flagged: boolean; flag_action: FlagAction },
) {
  for (const [key, data] of qc.getQueriesData<ImagesResponse>({ queryKey: ['images'] })) {
    if (!data) continue;
    qc.setQueryData<ImagesResponse>(key, {
      ...data,
      images: data.images.map((im) => (im.id === id ? { ...im, ...patch } : im)),
    });
  }
}

/**
 * Optimistic flagging with rollback — closes the silent-fail P1. The tile/inspector
 * updates instantly; on error the cache is restored and the mutation exposes
 * `isError`/`error` for inline surfacing.
 */
export function useFlagImage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: FlagAction }) => flagImage(id, action),
    onMutate: async ({ id, action }) => {
      await qc.cancelQueries({ queryKey: ['images'] });
      const prev = qc.getQueriesData<ImagesResponse>({ queryKey: ['images'] });
      patchImagesCache(qc, id, { flagged: true, flag_action: action });
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      for (const [key, data] of ctx?.prev ?? []) qc.setQueryData(key, data);
    },
    onSettled: (_d, _e, { id }) => {
      void qc.invalidateQueries({ queryKey: ['images'] });
      void qc.invalidateQueries({ queryKey: keys.imageDetail(id) });
    },
  });
}

/** Bulk flag for training-mode / multi-select triage. */
export function useBatchFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ids, action }: { ids: number[]; action: FlagAction }) => batchFlag(ids, action),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['images'] });
    },
  });
}

export function useAddLabel(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ value, category }: { value: string; category?: string }) =>
      addLabel(id, value, category),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.labels(id) });
    },
  });
}

export function useDeleteLabel(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (labelId: number) => deleteLabel(id, labelId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.labels(id) });
    },
  });
}

// ---- Custom label sets (Wave 2b) ----

/** All label sets + their values. Colors are DATA, applied inline at the chip. */
export function useLabelSets() {
  return useQuery({
    queryKey: keys.labelSets,
    queryFn: ({ signal }) => listLabelSets(signal),
    staleTime: 60_000,
  });
}

/** The label assignments (rows with set_id) for one image. */
export function useImageLabels(id: number | null) {
  return useQuery({
    queryKey: keys.imageLabels(id ?? -1),
    queryFn: ({ signal }) => getImageLabels(id as number, signal),
    enabled: id !== null,
    staleTime: 30_000,
  });
}

/** Assign a value (single-select replaces server-side). Optimistic on the
 *  image-labels cache: single-select swaps the set's row in place, multi
 *  appends a provisional row. A negative id marks the row provisional until the
 *  POST resolves; onSettled refetches the authoritative rows. */
export function useAssignLabel(imageId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ setId, value }: { setId: number; value: string }) =>
      assignLabel(imageId, setId, value),
    onMutate: async ({ setId, value }) => {
      const key = keys.imageLabels(imageId);
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<ImageLabel[]>(key);
      // single_select drives swap-vs-append; read it from the cached sets.
      const sets = qc.getQueryData<LabelSet[]>(keys.labelSets);
      const single = sets?.find((s) => s.id === setId)?.single_select === 1;
      const provisional: ImageLabel = {
        id: -Date.now(),
        image_id: imageId,
        set_id: setId,
        category: '',
        value,
      };
      const base = prev ?? [];
      const next = single
        ? [...base.filter((l) => l.set_id !== setId), provisional]
        : [...base, provisional];
      qc.setQueryData<ImageLabel[]>(key, next);
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx) qc.setQueryData(keys.imageLabels(imageId), ctx.prev);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.imageLabels(imageId) });
      void qc.invalidateQueries({ queryKey: ['images'] });
    },
  });
}

export function useUnassignLabel(imageId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (labelId: number) => unassignLabel(imageId, labelId),
    onMutate: async (labelId) => {
      const key = keys.imageLabels(imageId);
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<ImageLabel[]>(key);
      qc.setQueryData<ImageLabel[]>(
        key,
        (prev ?? []).filter((l) => l.id !== labelId),
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx) qc.setQueryData(keys.imageLabels(imageId), ctx.prev);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.imageLabels(imageId) });
      void qc.invalidateQueries({ queryKey: ['images'] });
    },
  });
}

// ---- Label-set CRUD (Settings manager, Task D) ----

export function useCreateLabelSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateSetBody) => createLabelSet(body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.labelSets }),
  });
}

export function useDeleteLabelSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (setId: number) => deleteLabelSet(setId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.labelSets }),
  });
}

export function usePatchLabelSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ setId, body }: { setId: number; body: PatchSetBody }) =>
      patchLabelSet(setId, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.labelSets }),
  });
}

export function useAddLabelValue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      setId,
      value,
      color,
    }: {
      setId: number;
      value: string;
      color?: string | null;
    }) => addLabelValue(setId, value, color),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.labelSets }),
  });
}

export function useRemoveLabelValue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ setId, valueId }: { setId: number; valueId: number }) =>
      removeLabelValue(setId, valueId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.labelSets }),
  });
}

// ---- Collections ----

export function useCollections() {
  return useQuery({
    queryKey: keys.collections,
    queryFn: ({ signal }) => listCollections(signal),
    staleTime: 30_000,
  });
}

export function useCreateCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, description }: { name: string; description?: string }) =>
      createCollection(name, description),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.collections });
    },
  });
}

export function useDeleteCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteCollection(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.collections });
    },
  });
}

export function useAddToCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ collectionId, imageId }: { collectionId: number; imageId: number }) =>
      addToCollection(collectionId, imageId),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.collections });
      void qc.invalidateQueries({ queryKey: ['images'] });
    },
  });
}

export function useRemoveFromCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ collectionId, imageId }: { collectionId: number; imageId: number }) =>
      removeFromCollection(collectionId, imageId),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.collections });
      void qc.invalidateQueries({ queryKey: ['images'] });
    },
  });
}

// ---- Canonical rating-set (optimistic, mirrors useFlagImage) ----

export function useSetRating() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, value }: { id: number; value: Rating }) => setRating(id, value),
    onMutate: async ({ id, value }) => {
      await qc.cancelQueries({ queryKey: ['images'] });
      const prev = qc.getQueriesData<ImagesResponse>({ queryKey: ['images'] });
      for (const [key, data] of prev) {
        if (!data) continue;
        qc.setQueryData<ImagesResponse>(key, {
          ...data,
          images: data.images.map((im) => (im.id === id ? { ...im, rating: value } : im)),
        });
      }
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      for (const [key, data] of ctx?.prev ?? []) qc.setQueryData(key, data);
    },
    onSettled: (_d, _e, { id }) => {
      void qc.invalidateQueries({ queryKey: ['images'] });
      void qc.invalidateQueries({ queryKey: keys.imageDetail(id) });
    },
  });
}

// ---- Exclusion rules (read + enable toggle) ----

export function useExclusions() {
  return useQuery({
    queryKey: keys.exclusions,
    queryFn: ({ signal }) => listExclusions(signal),
    staleTime: 60_000,
  });
}

export function useToggleExclusion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ruleId, enabled }: { ruleId: number; enabled: boolean }) =>
      toggleExclusion(ruleId, enabled),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.exclusions });
      void qc.invalidateQueries({ queryKey: ['images'] });
    },
  });
}

// ---- Video pillar ----

export function useVideos(filter: VideoFilter) {
  return useQuery({
    queryKey: keys.videos(filter),
    queryFn: ({ signal }) => listVideos(filter, signal),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });
}

export function useVideoFacets() {
  return useQuery({
    queryKey: keys.videoFacets,
    queryFn: ({ signal }) => getVideoFacets(signal),
    staleTime: 60_000,
  });
}

export function useVideoDetail(id: number | null) {
  return useQuery({
    queryKey: keys.video(id ?? -1),
    queryFn: ({ signal }) => getVideoDetail(id as number, signal),
    enabled: id !== null,
    staleTime: 30_000,
  });
}

// ---- Preference / active-learning scaffold ----

export function usePreferenceStatus() {
  return useQuery({
    queryKey: keys.preferenceStatus,
    queryFn: ({ signal }) => getPreferenceStatus(signal),
    staleTime: 30_000,
    retry: false,
  });
}

// ---- Training learning loop: exclude/hide suggestions + recommend/edge feeds ----

export function useExclusionSuggestions(minCount = 3) {
  return useQuery({
    queryKey: ['suggestions', 'exclusions', minCount],
    queryFn: ({ signal }) => fetchExclusionSuggestions(minCount, signal),
    staleTime: 15_000,
    retry: false,
  });
}

export function useCreateExclusion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ category, value }: { category: string; value: string }) =>
      createExclusion(category, value),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['suggestions'] });
      void qc.invalidateQueries({ queryKey: keys.exclusions });
      void qc.invalidateQueries({ queryKey: ['images'] });
    },
  });
}

/** Recommend / edge-case feed for Training mode. `enabled` gates the fetch to the
 *  active queue source so the inactive feed isn't polled. */
export function usePreferenceFeed(kind: 'recommend' | 'edge-cases', enabled = true) {
  return useQuery({
    queryKey: ['preference', 'feed', kind],
    queryFn: ({ signal }) => fetchPreferenceFeed(kind, 60, signal),
    enabled,
    retry: false,
  });
}
