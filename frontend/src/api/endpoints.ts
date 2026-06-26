import { getJson, postJson, qs } from './client';
import type {
  BatchFlagResult,
  Collection,
  CollectionDetail,
  CollectionListResponse,
  DirectoryStats,
  ExclusionRule,
  ExclusionSuggestions,
  ExclusionsResponse,
  Facets,
  ImageDetail,
  ImageItem,
  ImagesResponse,
  PipelineInfo,
  PreferenceFeed,
  PreferenceStatus,
  SearchMode,
  SearchResponse,
  Stats,
  SystemInfo,
  Throughput,
  UserLabel,
  UserLabels,
  VideoDetail,
  VideoFacets,
  VideosResponse,
} from './types';

/** The grid filter — matches the live /api/images query surface. */
/** Image sort keys — mirrors the backend VALID_SORTS + the store's SortKey. */
export type ImageSort =
  | 'recent'
  | 'created'
  | 'modified'
  | 'filename'
  | 'size'
  | 'random'
  | 'relevance';

/** Video sort keys — mirrors the backend VALID_VIDEO_SORTS. */
export type VideoSort = 'recent' | 'random' | 'filename' | 'size' | 'duration';

export interface ImageFilter {
  q?: string | null;
  person?: string | null;
  rating?: string | null;
  /** Single active (category,value) tag — the legacy /api/images surface. */
  category?: string | null;
  value?: string | null;
  /** Multi-tag AND — repeatable "category:value"; intersects across categories. */
  tags?: string[];
  /** Generic label-set filter — repeatable "set:value" (AND across, OR within). */
  labels?: string[];
  sort?: ImageSort;
  processed?: boolean | null;
  flagged?: boolean | null;
  /** Filter to a collection's members (server-side JOIN on collection_items). */
  collectionId?: number | null;
  exclude?: boolean;
  page?: number;
  limit?: number;
}

export function getStats(signal?: AbortSignal): Promise<Stats> {
  return getJson<Stats>('/api/stats', signal);
}

export function getFacets(signal?: AbortSignal): Promise<Facets> {
  return getJson<Facets>('/api/facets', signal);
}

export function listImages(filter: ImageFilter, signal?: AbortSignal): Promise<ImagesResponse> {
  const query = qs({
    q: filter.q ?? null,
    person: filter.person ?? null,
    rating: filter.rating ?? null,
    category: filter.category ?? null,
    value: filter.value ?? null,
    tags: filter.tags ?? [],
    label: filter.labels ?? [],
    sort: filter.sort ?? 'recent',
    processed: filter.processed ?? null,
    flagged: filter.flagged ?? null,
    collection_id: filter.collectionId ?? null,
    exclude: filter.exclude ?? false,
    page: filter.page ?? 1,
    limit: filter.limit ?? 100,
  });
  return getJson<ImagesResponse>(`/api/images${query}`, signal);
}

// ---- Full image detail + monitoring + bulk + labels (added 2026-06-23) ----

export function getImageDetail(id: number, signal?: AbortSignal): Promise<ImageDetail> {
  return getJson<ImageDetail>(`/api/images/${id}`, signal);
}

export function getPipeline(signal?: AbortSignal): Promise<PipelineInfo> {
  return getJson<PipelineInfo>('/api/pipeline', signal);
}

export function getSystem(signal?: AbortSignal): Promise<SystemInfo> {
  return getJson<SystemInfo>('/api/system', signal);
}

export function getThroughput(minutes = 10, signal?: AbortSignal): Promise<Throughput> {
  return getJson<Throughput>(`/api/pipeline/throughput${qs({ minutes })}`, signal);
}

export function getDirectoryStats(signal?: AbortSignal): Promise<DirectoryStats> {
  return getJson<DirectoryStats>('/api/stats/directories', signal);
}

export function batchFlag(
  imageIds: number[],
  action: 'reject' | 'maybe' | 'keep',
): Promise<BatchFlagResult> {
  return postJson<BatchFlagResult>('/api/images/batch/flag', { image_ids: imageIds, action });
}

export function getLabels(id: number, signal?: AbortSignal): Promise<UserLabels> {
  return getJson<UserLabels>(`/api/images/${id}/labels`, signal);
}

/** POST is FORM-encoded (matches the backend's single-flag/notes convention). */
export function addLabel(id: number, value: string, category = 'user'): Promise<UserLabel> {
  const form = new FormData();
  form.set('value', value);
  form.set('category', category);
  return fetch(`/api/images/${id}/labels`, { method: 'POST', body: form }).then((r) => {
    if (!r.ok) throw new Error(`addLabel failed: ${r.status}`);
    return r.json() as Promise<UserLabel>;
  });
}

export function deleteLabel(id: number, labelId: number): Promise<{ ok: boolean; id: number }> {
  return fetch(`/api/images/${id}/labels/${labelId}`, { method: 'DELETE' }).then((r) => {
    if (!r.ok) throw new Error(`deleteLabel failed: ${r.status}`);
    return r.json() as Promise<{ ok: boolean; id: number }>;
  });
}

export function flagImage(
  imageId: number,
  action: 'reject' | 'maybe' | 'keep',
): Promise<{ ok: boolean; action: string }> {
  // FORM-encoded with field `action` — the backend is `action: str = Form(...)`,
  // matching the house single-field mutation convention (addLabel/setRating/notes).
  // (Was postJson({ flag_action }), which 422'd: wrong content-type + field name.)
  const form = new FormData();
  form.set('action', action);
  return fetch(`/api/images/${imageId}/flag`, { method: 'POST', body: form }).then((r) => {
    if (!r.ok) throw new Error(`flagImage failed: ${r.status}`);
    return r.json() as Promise<{ ok: boolean; action: string }>;
  });
}

// ---- Contract-ready (docs/specs/backend-search-api.md). These activate once
// the backend search endpoints land + Tier-1 embeddings exist. ----

export interface SearchParams {
  q?: string | null;
  tags?: string[]; // "category:value"
  labels?: string[]; // "set:value" (Wave 2b)
  mode?: SearchMode;
  rating?: string | null;
  person?: string | null;
  sort?: 'relevance' | 'recent' | 'random';
  page?: number;
  page_size?: number;
}

export function search(params: SearchParams, signal?: AbortSignal): Promise<SearchResponse> {
  const query = qs({
    q: params.q ?? null,
    tags: params.tags ?? [],
    label: params.labels ?? [],
    mode: params.mode ?? 'hybrid',
    rating: params.rating ?? null,
    person: params.person ?? null,
    sort: params.sort ?? 'relevance',
    page: params.page ?? 1,
    page_size: params.page_size ?? 60,
  });
  return getJson<SearchResponse>(`/api/search${query}`, signal);
}

export function similar(
  imageId: number,
  opts: { k?: number; tags?: string[] } = {},
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const query = qs({ k: opts.k ?? 24, tags: opts.tags ?? [] });
  return getJson<SearchResponse>(`/api/images/${imageId}/similar${query}`, signal);
}

// ---- Collections (CRUD; form-encoded POST to match addLabel/flag convention) ----

export function listCollections(signal?: AbortSignal): Promise<CollectionListResponse> {
  return getJson<CollectionListResponse>('/api/collections', signal);
}

export function getCollection(id: number, signal?: AbortSignal): Promise<CollectionDetail> {
  return getJson<CollectionDetail>(`/api/collections/${id}`, signal);
}

export function createCollection(name: string, description = ''): Promise<Collection> {
  const form = new FormData();
  form.set('name', name);
  form.set('description', description);
  return fetch('/api/collections', { method: 'POST', body: form }).then((r) => {
    if (!r.ok) throw new Error(`createCollection failed: ${r.status}`);
    return r.json() as Promise<Collection>;
  });
}

export function addToCollection(
  collectionId: number,
  imageId: number,
): Promise<{ ok: boolean; image_count: number }> {
  const form = new FormData();
  form.set('image_id', String(imageId));
  return fetch(`/api/collections/${collectionId}/items`, { method: 'POST', body: form }).then(
    (r) => {
      if (!r.ok) throw new Error(`addToCollection failed: ${r.status}`);
      return r.json() as Promise<{ ok: boolean; image_count: number }>;
    },
  );
}

export function removeFromCollection(
  collectionId: number,
  imageId: number,
): Promise<{ ok: boolean }> {
  return fetch(`/api/collections/${collectionId}/items/${imageId}`, { method: 'DELETE' }).then(
    (r) => {
      if (!r.ok) throw new Error(`removeFromCollection failed: ${r.status}`);
      return r.json() as Promise<{ ok: boolean }>;
    },
  );
}

export function deleteCollection(id: number): Promise<{ ok: boolean }> {
  return fetch(`/api/collections/${id}`, { method: 'DELETE' }).then((r) => {
    if (!r.ok) throw new Error(`deleteCollection failed: ${r.status}`);
    return r.json() as Promise<{ ok: boolean }>;
  });
}

// ---- Canonical rating-set (writes images.rating column; form-encoded POST) ----

export function setRating(id: number, value: string): Promise<{ ok: boolean; rating: string }> {
  const form = new FormData();
  form.set('value', value);
  return fetch(`/api/images/${id}/rating`, { method: 'POST', body: form }).then((r) => {
    if (!r.ok) throw new Error(`setRating failed: ${r.status}`);
    return r.json() as Promise<{ ok: boolean; rating: string }>;
  });
}

// ---- Exclusion rules (read + enable toggle over the live CRUD) ----

export function listExclusions(signal?: AbortSignal): Promise<ExclusionsResponse> {
  return getJson<ExclusionsResponse>('/api/exclusions', signal);
}

export function createExclusion(
  category: string,
  value: string,
): Promise<{ ok?: boolean; match_count?: number; id?: number }> {
  // FORM-encoded (backend: category/value = Form(...)) — house convention.
  const form = new FormData();
  form.set('category', category);
  form.set('value', value);
  return fetch('/api/exclusions', { method: 'POST', body: form }).then((r) => {
    if (!r.ok) throw new Error(`createExclusion failed: ${r.status}`);
    return r.json();
  });
}

export function fetchExclusionSuggestions(
  minCount = 3,
  signal?: AbortSignal,
): Promise<ExclusionSuggestions> {
  return getJson<ExclusionSuggestions>(`/api/suggestions/exclusions?min_count=${minCount}`, signal);
}

export function fetchPreferenceFeed(
  kind: 'recommend' | 'edge-cases',
  limit = 60,
  signal?: AbortSignal,
): Promise<PreferenceFeed> {
  return getJson<PreferenceFeed>(`/api/preference/${kind}?limit=${limit}`, signal);
}

export function toggleExclusion(ruleId: number, enabled: boolean): Promise<ExclusionRule> {
  const form = new FormData();
  form.set('enabled', String(enabled));
  return fetch(`/api/exclusions/${ruleId}`, { method: 'PATCH', body: form }).then((r) => {
    if (!r.ok) throw new Error(`toggleExclusion failed: ${r.status}`);
    return r.json() as Promise<ExclusionRule>;
  });
}

// ---- Video pillar (separate `videos` surface; unified grid is a follow-up) ----

export interface VideoFilter {
  person?: string | null;
  rating?: string | null;
  labels?: string[];
  orientation?: string | null;
  duration?: string | null;
  has_audio?: boolean | null;
  sort?: VideoSort;
  page?: number;
  limit?: number;
}

export function listVideos(filter: VideoFilter, signal?: AbortSignal): Promise<VideosResponse> {
  const query = qs({
    person: filter.person ?? null,
    rating: filter.rating ?? null,
    label: filter.labels ?? [],
    orientation: filter.orientation ?? null,
    duration: filter.duration ?? null,
    has_audio: filter.has_audio ?? null,
    sort: filter.sort ?? 'recent',
    page: filter.page ?? 1,
    limit: filter.limit ?? 100,
  });
  return getJson<VideosResponse>(`/api/videos${query}`, signal);
}

export function getVideoFacets(signal?: AbortSignal): Promise<VideoFacets> {
  return getJson<VideoFacets>('/api/videos/facets', signal);
}

export function getVideoDetail(id: number, signal?: AbortSignal): Promise<VideoDetail> {
  return getJson<VideoDetail>(`/api/videos/${id}`, signal);
}

export const videoPoster = (fileHash: string): string => `/media/video-poster/${fileHash}`;
export const videoStream = (fileHash: string): string => `/media/video/${fileHash}`;
export const videoVtt = (fileHash: string): string => `/media/video-vtt/${fileHash}`;

// ---- Preference / active-learning scaffold (degrades until labels + vectors) ----

export function getPreferenceStatus(signal?: AbortSignal): Promise<PreferenceStatus> {
  return getJson<PreferenceStatus>('/api/preference/status', signal);
}

export type { ImageItem };
