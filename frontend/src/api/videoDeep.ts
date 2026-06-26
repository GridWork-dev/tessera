// Deep-video API client — scene-level enrichment (tags / caption / transcript /
// face count) + per-video backfill trigger. Self-contained per-lane client so
// the shared endpoints.ts/types.ts stay untouched; mirrors client.ts conventions
// (getJson/postJson, ApiError surfacing). Endpoints under /api/video-deep, added
// by the wave-2 backend (webui/routes_video_deep.py).

import { getJson, postJson } from './client';

/** One ASR segment within a scene (ordered by segment_index server-side). */
export interface SceneTranscriptSegment {
  start_time: number | null;
  end_time: number | null;
  text: string;
  language: string | null;
}

/** A structured tag on a scene keyframe (Tier-0 style category/value). */
export interface SceneTag {
  category: string;
  value: string;
  confidence: number | null;
  tag_source: string | null;
}

export interface SceneCaption {
  model: string;
  caption: string;
}

/** Full scene detail — GET /api/video-deep/scenes/{id}. */
export interface SceneDetailResponse {
  id: number;
  video_id: number;
  scene_index: number | null;
  start_time: number | null;
  end_time: number | null;
  keyframe_path: string | null;
  caption: string | null;
  processed: number;
  tags: SceneTag[];
  captions: SceneCaption[];
  transcript: SceneTranscriptSegment[];
  transcript_text: string;
  /** Detected-face count on the keyframe. Crop files are not yet web-served. */
  face_count: number;
}

/** A scene row with enrichment-status flags — items of the per-video list. */
export interface SceneListItem {
  id: number;
  scene_index: number | null;
  start_time: number | null;
  end_time: number | null;
  keyframe_path: string | null;
  processed: number;
  tagged: boolean;
  captioned: boolean;
  transcribed: boolean;
  face_count: number;
}

/** GET /api/video-deep/videos/{id}/scenes. */
export interface VideoScenesResponse {
  video_id: number;
  scenes: SceneListItem[];
}

/** POST /api/video-deep/videos/{id}/backfill — returns immediately. */
export interface BackfillResponse {
  status: string;
  video_id: number;
}

export function getSceneDetail(
  sceneId: number,
  signal?: AbortSignal,
): Promise<SceneDetailResponse> {
  return getJson<SceneDetailResponse>(`/api/video-deep/scenes/${sceneId}`, signal);
}

export function getVideoScenes(
  videoId: number,
  signal?: AbortSignal,
): Promise<VideoScenesResponse> {
  return getJson<VideoScenesResponse>(`/api/video-deep/videos/${videoId}/scenes`, signal);
}

export function triggerVideoBackfill(videoId: number): Promise<BackfillResponse> {
  return postJson<BackfillResponse>(`/api/video-deep/videos/${videoId}/backfill`);
}
