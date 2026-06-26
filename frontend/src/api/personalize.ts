// Personalization (rungs 1-2) client — few-shot linear PROBE + active-learning
// queue, served under /api/personalize. Standalone per-lane client (does NOT
// touch the shared endpoints.ts); follows client.ts conventions: getJson for
// reads, postJson for JSON bodies. Response shapes mirror pipeline/personalize.
//
// Backend contracts (pipeline/personalize/api.py):
//   POST /api/personalize/probe/preview        -> ProbePreview
//   POST /api/personalize/probe/apply          -> ProbeApply (dry-run default)
//   GET  /api/personalize/active-learning/next  -> ActiveLearningNext

import { getJson, postJson, qs } from './client';

// ---- Response types ----

/** A single (image_id, score) pair from a probe preview's top-scoring sample. */
export type ProbeSample = [number, number];

/** READ-ONLY preview: how many images a fitted probe would tag at `threshold`. */
export interface ProbePreview {
  count: number;
  threshold: number;
  total: number;
  n_pos: number;
  n_neg: number;
  /** Top-scoring above-threshold images: [image_id, probability][]. */
  sample: ProbeSample[];
}

/** Apply result: a preview plus the write outcome. `written` is 0 on dry-run. */
export interface ProbeApply extends ProbePreview {
  dry_run: boolean;
  written: number;
}

/** One uncertain image the loop proposes for the human to label next. */
export interface ActiveLearningProposal {
  image_id: number;
  /** Source-image file_hash for the thumbnail — sent with the queue so the card
   *  renders without a getImageDetail fetch per proposal. */
  file_hash: string | null;
  probability: number;
  margin: number;
}

/** Active-learning queue. `ready` is false during cold start (needs both a
 *  keep and a reject label); `reason` explains the ordering / cold-start state. */
export interface ActiveLearningNext {
  ready: boolean;
  n_pos: number;
  n_neg: number;
  n_unlabeled: number;
  proposals: ActiveLearningProposal[];
  reason: string;
}

// ---- Calls ----

export interface ProbePreviewBody {
  pos_ids: number[];
  neg_ids: number[];
  threshold?: number;
  sample?: number;
}

export function probePreview(body: ProbePreviewBody): Promise<ProbePreview> {
  return postJson<ProbePreview>('/api/personalize/probe/preview', body);
}

export interface ProbeApplyBody {
  pos_ids: number[];
  neg_ids: number[];
  category: string;
  value: string;
  threshold?: number;
  confidence?: number | null;
  /** Dry-run is the backend DEFAULT; pass false to actually write tags. */
  dry_run?: boolean;
}

export function probeApply(body: ProbeApplyBody): Promise<ProbeApply> {
  return postJson<ProbeApply>('/api/personalize/probe/apply', body);
}

export function activeLearningNext(count = 20, signal?: AbortSignal): Promise<ActiveLearningNext> {
  return getJson<ActiveLearningNext>(
    `/api/personalize/active-learning/next${qs({ count })}`,
    signal,
  );
}
