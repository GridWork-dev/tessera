// Server capability gates (Wave 2b; backend webui/routes_capabilities.py). These
// are the SERVER axis (faces/geo/video/license) — distinct from user visibility
// (ui-prefs). A gated-off module is hidden regardless of user prefs.

import { getJson } from './client';

export interface Capabilities {
  faces: boolean;
  geo: boolean;
  video: boolean;
  license: boolean;
}

export function getCapabilities(signal?: AbortSignal): Promise<Capabilities> {
  return getJson<Capabilities>('/api/capabilities', signal);
}
