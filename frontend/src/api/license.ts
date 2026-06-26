// License panel client (Spec J / PART 5). Mirrors api/client.ts conventions:
// getJson / postJson / delJson over the JSON surface. Verification is OFFLINE —
// the backend checks an Ed25519 signature against a baked-in public key; nothing
// here phones home. Response shapes are defined HERE (api/types.ts is owned by
// other lanes and must not be edited).
//
// Backend: webui/routes_commerce.py — GET/POST/DELETE /api/license.

import { delJson, getJson, postJson } from './client';

/** The three (and only) capabilities Pro unlocks. No content is ever gated. */
export interface ProFeatures {
  bulk_export: boolean;
  remote_compute_routing: boolean;
  priority_support: boolean;
}

export interface LicenseStatus {
  tier: 'community' | 'pro';
  features: ProFeatures;
  /** Human status line, e.g. "Pro — perpetual (v1)" or "Free". */
  detail: string;
  /** Highest app MAJOR version a Pro token grants Pro on; null for community. */
  max_version: number | null;
}

export interface LicenseMutation {
  ok: boolean;
  tier: 'community' | 'pro';
  detail?: string;
  error?: string;
}

export const getLicense = (signal?: AbortSignal): Promise<LicenseStatus> =>
  getJson<LicenseStatus>('/api/license', signal);

/** Save a pasted token LOCALLY (writes license.key) and re-resolve entitlement. */
export const saveLicense = (token: string): Promise<LicenseMutation> =>
  postJson<LicenseMutation>('/api/license', { token });

/** Remove the local license.key — reverts to Free. Never bricks anything. */
export const removeLicense = (): Promise<LicenseMutation> =>
  delJson<LicenseMutation>('/api/license');

// Pro is in active development — Polar checkout isn't live yet. While this is
// false, Settings → License renders a "Coming soon" card instead of the
// activation flow (the offline-verify backend stays in place, dormant). Flip to
// true once checkout ships. Mirrors the marketing site's config.ts PRO_AVAILABLE.
export const PRO_AVAILABLE = false;
