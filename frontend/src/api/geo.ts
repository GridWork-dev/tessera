// Geo lane data access — Places, Events, event detail, backfill (/api/geo).
//
// Per-feature client following src/api/client.ts conventions; response types
// live here (NOT in the shared types.ts) so the geo lane stays self-contained.
// The backend router is webui/routes_geo.py (prefix /api/geo).

import { ApiError, getJson, postJson } from './client';

/** A reverse-geocoded place; image_count is how many images resolve to it. */
export interface Place {
  id: number;
  name: string;
  admin1: string | null;
  cc: string | null;
  lat: number | null;
  lon: number | null;
  image_count: number;
}

/** An auto-album (event) — a time/space cluster of media. */
export interface GeoEvent {
  id: number;
  start_time: string | null;
  end_time: string | null;
  centroid_lat: number | null;
  centroid_lon: number | null;
  member_count: number;
  label: string | null;
}

/** One event member. owner_type is 'image' (videos fold in later). */
export interface EventMember {
  owner_type: string;
  owner_id: number;
}

export interface EventDetail extends GeoEvent {
  members: EventMember[];
}

export type BackfillStage = 'gps' | 'places' | 'events' | 'scene_tags';

export interface BackfillResult {
  stage: string;
  dry_run: boolean;
  [key: string]: unknown;
}

/** Places, descending by image count. Returns [] before the geo backfill runs. */
export function listPlaces(signal?: AbortSignal): Promise<Place[]> {
  return getJson<Place[]>('/api/geo/places', signal);
}

/** Events (auto-albums), newest first. Returns [] before the geo backfill runs. */
export function listEvents(signal?: AbortSignal): Promise<GeoEvent[]> {
  return getJson<GeoEvent[]>('/api/geo/events', signal);
}

/** One event plus its member image ids. 404s for an unknown id. */
export function getEventDetail(eventId: number, signal?: AbortSignal): Promise<EventDetail> {
  return getJson<EventDetail>(`/api/geo/events/${eventId}`, signal);
}

/** Trigger a backfill stage. Defaults to a dry run (writes nothing). */
export function triggerBackfill(stage: BackfillStage, dryRun = true): Promise<BackfillResult> {
  return postJson<BackfillResult>('/api/geo/backfill', { stage, dry_run: dryRun });
}

/** Member thumbnail: members carry an image id only (no file_hash), so resolve
 *  via the id-keyed content route rather than /media/thumb/{file_hash}. */
export const memberThumb = (imageId: number): string => `/image-content/${imageId}`;

export { ApiError };
