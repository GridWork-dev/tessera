// API response shapes. Mirrors the live FastAPI backend (webui/main.py) for
// the endpoints that exist today, and docs/specs/backend-search-api.md for the
// search/facets/similar endpoints being added.

export type Rating = 'unrated' | 'sfw' | 'suggestive' | 'nsfw';

export interface TagRef {
  category: string;
  value: string;
  confidence: number | null;
}

/** A single asset as returned by /api/images and (rescored) /api/search. */
export interface ImageItem {
  id: number;
  file_hash: string;
  filename: string;
  person: string | null;
  width: number | null;
  height: number | null;
  rating: string | null;
  processed: boolean;
  flagged: boolean;
  flag_action: string | null;
  tags: TagRef[];
}

/** Per-label-set value counts under the current filter (Wave 2b, disjunctive). */
export type LabelFacets = Record<string, Record<string, number>>;

export interface ImagesResponse {
  images: ImageItem[];
  total: number;
  page: number;
  total_pages: number;
  /** Per-label-set facet counts (present once migration 013 has run). */
  label_facets?: LabelFacets;
}

// ---- Custom label sets (Wave 2b; migration 013). Colors are DATA. ----

export interface LabelValue {
  id: number;
  value: string;
  color: string | null;
  sort_order: number;
}

export interface LabelSet {
  id: number;
  name: string;
  single_select: number; // 0 | 1 (SQLite int)
  color: string | null;
  sort_order: number;
  is_system: number; // 0 | 1
  values: LabelValue[];
}

/** One assigned label row (user_labels with set_id). */
export interface ImageLabel {
  id: number;
  image_id: number;
  set_id: number;
  category: string;
  value: string;
}

export interface Stats {
  total_images: number;
  processed_images: number;
  processing_pct: number;
  flagged_count: number;
  people_count: number;
  tag_categories: number;
}

export interface FacetValue {
  value: string;
  count: number;
}

/** Live /api/facets shape (webui/main.py). */
export interface Facets {
  people: Record<string, number>;
  categories: Record<string, number>;
  tags_by_category: Record<string, FacetValue[]>;
  ratings: string[];
  flag_actions: Record<string, number>;
}

// ---- Hybrid search (docs/specs/backend-search-api.md). Contract-ready. ----

export type SearchMode = 'tags' | 'caption' | 'semantic' | 'text2image' | 'hybrid';

export interface ScoreParts {
  vector?: number;
  fts?: number;
  rrf?: number;
}

export interface SearchResultItem {
  id: number;
  file_hash: string;
  score: number;
  score_parts?: ScoreParts;
  rating: string | null;
  person: string | null;
  width?: number | null;
  height?: number | null;
  tags: TagRef[];
}

export interface SearchResponse {
  results: SearchResultItem[];
  total: number;
  page: number;
  page_size: number;
  mode: SearchMode;
  /** Set by the backend when vectors are not yet populated (Tier 1 pending). */
  vectors_unavailable?: boolean;
  /** Set when the backend served a fallback mode (e.g. semantic gate off →
   *  degraded to tag matches). Holds the originally-requested mode. */
  degraded_from?: SearchMode;
}

// ---- Full image detail (GET /api/images/{id}) — one round trip for the
// in-depth inspector. captions empty until Tier 2; nudenet_regions null until
// Tier 3; has_embedding false until Tier 1. ----

export interface DetailTag {
  category: string | null;
  value: string | null;
  confidence: number | null;
  tag_source: string;
}

export interface Caption {
  model: string | null;
  caption: string | null;
}

export interface NudeRegion {
  label: string;
  score: number;
  box: number[];
}

export interface ImageDetail {
  id: number;
  path: string;
  filename: string | null;
  directory: string | null;
  person: string | null;
  file_hash: string | null;
  width: number | null;
  height: number | null;
  filesize: number | null;
  format: string | null;
  created_at: string | null;
  modified_at: string | null;
  imported_at: string | null;
  media_type: string;
  // Sourced from the Rating label set now (Wave 2c) — null when unrated.
  rating: string | null;
  processed: boolean;
  flagged: boolean;
  flag_action: 'reject' | 'maybe' | 'keep' | null;
  original_path: string | null;
  original_filename: string | null;
  has_metadata: boolean;
  has_thumbnail: boolean;
  tags: DetailTag[];
  notes: string | null;
  captions: Caption[];
  nudenet_regions: NudeRegion[] | null;
  has_embedding: boolean;
  similar_available: boolean;
}

// ---- Monitoring: /api/pipeline, /api/system, /api/pipeline/throughput ----

export interface TierProgress {
  processed?: number;
  count?: number;
  total: number;
  pct: number;
  running?: boolean;
}

export interface PipelineInfo {
  total: number;
  tier0_3: TierProgress;
  tier1: TierProgress;
  tier2: TierProgress;
  tier3: TierProgress;
}

export interface MemInfo {
  total: number;
  available?: number;
  used?: number;
  percent: number;
}

export interface DiskInfo {
  total: number;
  used?: number;
  free: number;
  percent: number;
}

export interface SystemInfo {
  cpu_percent: number;
  cpu_count: number;
  per_cpu_percent?: number[];
  virtual_memory: MemInfo;
  disk_usage: DiskInfo;
  load_average?: number[];
  gpu?: { available: boolean; backend?: string } | null;
  tagger_running: boolean;
}

export interface Throughput {
  window_minutes: number;
  count: number;
  per_minute: number;
  signal: 'imported_at';
  latest_at: string | null;
}

// ---- Directory / person stats (GET /api/stats/directories) ----

export interface DirStat {
  key: string;
  image_count: number;
  processed_count: number;
  flagged_count: number;
  ratings: Record<string, number>;
}

export interface DirectoryStats {
  by_person: DirStat[];
  by_directory: DirStat[];
}

// ---- Bulk flag + user labels ----

export interface BatchFlagResult {
  ok: boolean;
  updated: number;
  results: ({ id: number; ok: true; action: string } | { id: number; ok: false; error: string })[];
}

export interface UserLabel {
  id: number;
  category: string;
  value: string;
  created_at: string;
}

export interface UserLabels {
  labels: UserLabel[];
}

// ---- Collections (GET/POST/DELETE /api/collections*) ----

export interface Collection {
  id: number;
  name: string;
  description: string | null;
  cover_image_id: number | null;
  created_at: string | null;
  image_count: number;
}

export interface CollectionListResponse {
  collections: Collection[];
}

export interface CollectionDetail {
  id: number;
  name: string;
  description: string | null;
  cover_image_id: number | null;
  created_at: string | null;
  image_ids: number[];
  image_count: number;
}

// ---- Exclusion rules (GET/PATCH /api/exclusions) ----

export interface ExclusionRule {
  id: number;
  category: string;
  value: string;
  enabled: boolean;
  match_count: number;
  source?: string;
  created_at?: string | null;
}

export interface ExclusionsResponse {
  rules: Record<string, ExclusionRule[]>;
  total: number;
}

// ---- Video pillar (GET /api/videos*) ----

export interface VideoItem {
  id: number;
  file_hash: string | null;
  filename: string | null;
  person: string | null;
  width: number | null;
  height: number | null;
  duration: number | null;
  duration_bucket: string | null;
  orientation: string | null;
  fps: number | null;
  codec: string | null;
  has_audio: boolean;
  rating: string | null;
  media_type: 'video';
  processed: number;
  has_poster: boolean;
  has_sprite: boolean;
  /** Group B: 1 = user pinned this poster (auto re-pick skips it). */
  poster_locked?: boolean;
}

export interface VideosResponse {
  videos: VideoItem[];
  total: number;
  page: number;
  total_pages: number;
}

export interface VideoScene {
  scene_index: number | null;
  start_time: number | null;
  end_time: number | null;
  caption: string | null;
}

export interface VideoDetail extends VideoItem {
  path: string | null;
  directory: string | null;
  bitrate: number | null;
  filesize: number | null;
  scenes: VideoScene[];
}

export interface VideoFacets {
  duration: Record<string, number>;
  orientation: Record<string, number>;
  has_audio: { yes: number; no: number };
  people: Record<string, number>;
  ratings: Record<string, number>;
}

// ---- Preference / active-learning scaffold (GET /api/preference/*) ----

export interface PreferenceStatus {
  keep: number;
  reject: number;
  maybe: number;
  vectors: number;
  min_per_class: number;
  trainable: boolean;
  reason: string | null;
}

// ---- Training learning loop: exclude/hide suggestions + preference feeds ----

export interface ExclusionCandidate {
  category: string;
  value: string;
  reject_count: number;
  sample_image_ids: number[];
}

export interface ExclusionSuggestions {
  candidates: ExclusionCandidate[];
  reasons: { value: string; count: number }[];
  reject_count: number;
  min_count: number;
}

/** Recommend / edge-case feed. Degrades to items:[] + reason until trained. */
export interface PreferenceFeed {
  items: ImageItem[];
  degraded?: boolean;
  reason?: string | null;
  counts?: PreferenceStatus;
}
