// Tiny typed fetch wrapper. Relative URLs hit the same origin; in dev, Vite
// proxies /api, /media, /image-content to the backend (vite.config.ts).

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** Build a query string, dropping null/undefined and expanding arrays (repeatable params). */
export function qs(
  params: Record<string, string | number | boolean | string[] | null | undefined>,
): string {
  const sp = new URLSearchParams();
  for (const [key, val] of Object.entries(params)) {
    if (val === null || val === undefined || val === '') continue;
    if (Array.isArray(val)) {
      for (const v of val) sp.append(key, v);
    } else {
      sp.set(key, String(val));
    }
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, {
    signal: signal ?? null,
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? null : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const errBody = (await res.json()) as { detail?: string };
      if (errBody.detail) detail = errBody.detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export async function delJson<T>(path: string): Promise<T> {
  const res = await fetch(path, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const errBody = (await res.json()) as { detail?: string };
      if (errBody.detail) detail = errBody.detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/** JSON body request for a given method (PUT/PATCH). Mirrors postJson. */
async function bodyJson<T>(method: 'PUT' | 'PATCH', path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? null : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const errBody = (await res.json()) as { detail?: string };
      if (errBody.detail) detail = errBody.detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export function putJson<T>(path: string, body?: unknown): Promise<T> {
  return bodyJson<T>('PUT', path, body);
}

export function patchJson<T>(path: string, body?: unknown): Promise<T> {
  return bodyJson<T>('PATCH', path, body);
}

/** Thumbnail / full-res media are served by file_hash. */
export const mediaThumb = (fileHash: string): string => `/media/thumb/${fileHash}`;
export const mediaFull = (fileHash: string): string => `/media/full/${fileHash}`;
