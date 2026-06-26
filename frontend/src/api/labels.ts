// Custom label-sets API (Wave 2b; backend webui/routes_labels.py). All paths
// under /api/label-sets. Colors are DATA (label_definitions.color), never theme.

import { delJson, getJson, patchJson, postJson } from './client';
import type { ImageLabel, LabelSet } from './types';

export function listLabelSets(signal?: AbortSignal): Promise<LabelSet[]> {
  return getJson<LabelSet[]>('/api/label-sets', signal);
}

export function getImageLabels(imageId: number, signal?: AbortSignal): Promise<ImageLabel[]> {
  return getJson<ImageLabel[]>(`/api/label-sets/images/${imageId}`, signal);
}

export interface AssignResult {
  id: number;
  image_id: number;
  set_id: number;
  value: string;
}

/** Assign a value (single-select sets replace the prior value server-side). */
export function assignLabel(imageId: number, setId: number, value: string): Promise<AssignResult> {
  return postJson<AssignResult>(`/api/label-sets/images/${imageId}`, { set_id: setId, value });
}

export function unassignLabel(
  imageId: number,
  labelId: number,
): Promise<{ ok: boolean; label_id: number }> {
  return delJson<{ ok: boolean; label_id: number }>(`/api/label-sets/images/${imageId}/${labelId}`);
}

// ---- Set / value CRUD (Settings manager, Task D) ----

export interface CreateSetBody {
  name: string;
  single_select?: boolean;
  color?: string | null;
}

export function createLabelSet(body: CreateSetBody): Promise<{ id: number; name: string }> {
  return postJson<{ id: number; name: string }>('/api/label-sets', body);
}

export interface PatchSetBody {
  name?: string;
  single_select?: boolean;
  color?: string | null;
  sort_order?: number;
}

export function patchLabelSet(
  setId: number,
  body: PatchSetBody,
): Promise<{ ok: boolean; set_id: number }> {
  return patchJson<{ ok: boolean; set_id: number }>(`/api/label-sets/${setId}`, body);
}

export function deleteLabelSet(setId: number): Promise<{ ok: boolean; set_id: number }> {
  return delJson<{ ok: boolean; set_id: number }>(`/api/label-sets/${setId}`);
}

export function addLabelValue(
  setId: number,
  value: string,
  color?: string | null,
): Promise<{ id: number; set_id: number; value: string }> {
  return postJson<{ id: number; set_id: number; value: string }>(
    `/api/label-sets/${setId}/values`,
    { value, color: color ?? null },
  );
}

export function removeLabelValue(
  setId: number,
  valueId: number,
): Promise<{ ok: boolean; value_id: number }> {
  return delJson<{ ok: boolean; value_id: number }>(`/api/label-sets/${setId}/values/${valueId}`);
}
