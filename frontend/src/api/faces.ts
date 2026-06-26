// Faces / People client — per-feature file (lane: people). Mirrors the house
// conventions in api/client.ts: getJson/postJson for the JSON surface, a thin
// fetch().then(...) for DELETE. Response shapes are defined HERE (the shared
// api/types.ts is owned by other lanes and must not be edited).
//
// The whole /api/faces surface is gated by the off-by-default `faces.enabled`
// switch: when dark, every endpoint returns HTTP 403. ApiError carries the
// status so the UI can distinguish "feature disabled" from "real failure".

import { ApiError, getJson, postJson } from './client';

/** A person / face cluster. `cover_face_id` is the lowest-id face (a stable cover). */
export interface Person {
  id: number;
  name: string | null;
  cover_face_id: number | null;
  /** Source image of the cover face — lets the grid render a real cover thumbnail. */
  cover_image_id: number | null;
  /** file_hash of the cover face's source image — render the cover thumb directly
   *  (no per-person detail fetch). */
  cover_image_hash: string | null;
  face_count: number;
  created_at: string;
  updated_at: string;
}

/** A single detected face. Carries `image_id` (the source image) + bbox. */
export interface Face {
  id: number;
  image_id: number;
  /** file_hash of the source image — render the face thumb without a detail fetch. */
  file_hash: string | null;
  person_id: number | null;
  bbox: number[] | null;
  embedding_dim: number;
  detector: string;
  embedder: string;
  confidence: number;
  created_at: string;
}

export interface ClusterResult {
  faces_considered: number;
  clusters_created: number;
  faces_assigned: number;
  noise: number;
}

/** Re-exported so callers can `instanceof`-check the 403 disabled state. */
export { ApiError };

// ---- reads ---------------------------------------------------------------- //

export function listPeople(signal?: AbortSignal): Promise<Person[]> {
  return getJson<Person[]>('/api/faces/people', signal);
}

export function facesForPerson(personId: number, signal?: AbortSignal): Promise<Face[]> {
  return getJson<Face[]>(`/api/faces/people/${personId}/faces`, signal);
}

export function facesForImage(imageId: number, signal?: AbortSignal): Promise<Face[]> {
  return getJson<Face[]>(`/api/faces/images/${imageId}/faces`, signal);
}

// ---- clustering ----------------------------------------------------------- //

export function runClustering(): Promise<ClusterResult> {
  return postJson<ClusterResult>('/api/faces/cluster');
}

// ---- mutations ------------------------------------------------------------ //

export function namePerson(
  personId: number,
  name: string,
): Promise<{ ok: boolean; person_id: number; name: string }> {
  // JSON body (backend: NameBody pydantic model — NOT form-encoded).
  return postJson(`/api/faces/people/${personId}/name`, { name });
}

export function mergePeople(
  sourceId: number,
  targetId: number,
): Promise<{ ok: boolean; merged_into: number }> {
  return postJson('/api/faces/people/merge', { source_id: sourceId, target_id: targetId });
}

export function splitFace(
  faceId: number,
): Promise<{ ok: boolean; face_id: number; new_person_id: number }> {
  return postJson(`/api/faces/faces/${faceId}/split`);
}

// ---- erasure (BIPA / GDPR Art.9) ------------------------------------------ //

export function deletePerson(
  personId: number,
): Promise<{ ok: boolean; person_id: number; faces_removed: number }> {
  return fetch(`/api/faces/people/${personId}`, { method: 'DELETE' }).then(async (r) => {
    if (!r.ok) throw new ApiError(r.status, r.statusText);
    return r.json() as Promise<{ ok: boolean; person_id: number; faces_removed: number }>;
  });
}

export function purgeAllFaces(): Promise<{ ok: boolean; faces_removed: number }> {
  return postJson('/api/faces/purge');
}
