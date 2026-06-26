// UI preferences blob (Wave 2b; backend webui/routes_ui_prefs.py). The USER
// visibility axis: nav order/hidden, dashboard order/hidden, module enable flags,
// theme. A single versioned JSON blob (whole-blob upsert), forward-compatible.

import { getJson, putJson } from './client';

export interface NavPrefs {
  order?: string[];
  hidden?: string[];
}

export interface UiPrefsBody {
  nav?: NavPrefs;
  dashboard?: NavPrefs;
  modules?: { enabled?: Record<string, boolean> };
  theme?: string;
}

export interface UiPrefs {
  version: number;
  ui: UiPrefsBody;
}

export function getUiPrefs(signal?: AbortSignal): Promise<UiPrefs> {
  return getJson<UiPrefs>('/api/ui-prefs', signal);
}

/** Whole-blob upsert (the backend replaces the stored blob). */
export function putUiPrefs(prefs: UiPrefs): Promise<UiPrefs> {
  return putJson<UiPrefs>('/api/ui-prefs', prefs);
}
