// First-run setup wizard client (lane: wave3 / Spec F). Mirrors the house
// conventions in api/client.ts: getJson/postJson over the JSON surface. Response
// shapes are defined HERE (the shared api/types.ts is owned by other lanes and
// must not be edited).
//
// Backend: webui/routes_setup.py — GET /api/setup/status + per-step POSTs.

import { getJson, postJson, qs } from './client';

export type ComputeBackend = 'local_mps' | 'local_cuda' | 'local_directml' | 'local_cpu';

export interface SetupStatus {
  first_run_needed: boolean;
  apply_enabled: boolean;
  config_path: string;
  steps: {
    library: { configured: boolean; content_root: string; library_root: string };
    weights: { offline_ready: boolean; required_missing: number };
    compute: {
      detected_backend: ComputeBackend;
      system: string;
      machine: string;
      apple_silicon: boolean;
    };
    auth: {
      admin_exists: boolean;
      auth_enabled: boolean;
      bind_host: string;
      bind_port: number;
    };
  };
}

export interface WeightsPlanRow {
  key: string;
  title: string;
  approx_size_mb: number;
  source: string;
}

export interface WeightsPlan {
  to_pull: WeightsPlanRow[];
  already_present: string[];
  count: number;
  approx_total_mb: number;
  approx_all_selected_mb: number;
}

export interface ComputeDetect {
  detected_backend: ComputeBackend;
  system: string;
  machine: string;
  apple_silicon: boolean;
  available_providers: string[];
  choices: ComputeBackend[];
}

// ---- reads ---------------------------------------------------------------- //

export const getSetupStatus = (signal?: AbortSignal): Promise<SetupStatus> =>
  getJson<SetupStatus>('/api/setup/status', signal);

export const getWeightsPlan = (
  opts: { includeOptional?: boolean; includeNudenet?: boolean } = {},
  signal?: AbortSignal,
): Promise<WeightsPlan> =>
  getJson<WeightsPlan>(
    `/api/setup/weights/plan${qs({
      include_optional: opts.includeOptional ?? true,
      include_nudenet: opts.includeNudenet ?? false,
    })}`,
    signal,
  );

export const getComputeDetect = (signal?: AbortSignal): Promise<ComputeDetect> =>
  getJson<ComputeDetect>('/api/setup/compute/detect', signal);

// ---- steps ---------------------------------------------------------------- //

export const setLibrary = (body: {
  library_root: string;
  content_root?: string;
}): Promise<{ ok: boolean; library_root: string; content_root: string }> =>
  postJson('/api/setup/library', body);

export const pullWeights = (body: {
  include_optional?: boolean;
  include_nudenet?: boolean;
  only?: string[];
}): Promise<{ applied: boolean; reason?: string; plan?: WeightsPlan }> =>
  postJson('/api/setup/weights/pull', body);

export const setCompute = (body: {
  backend: ComputeBackend | null;
}): Promise<{ ok: boolean; backend: ComputeBackend }> => postJson('/api/setup/compute', body);

export const setBindAuth = (body: {
  bind_host: string;
  bind_port: number;
  enable_auth: boolean;
  admin_username?: string;
  admin_password?: string;
}): Promise<{ ok: boolean; auth_enabled: boolean; admin_seeded: boolean }> =>
  postJson('/api/setup/auth', body);
