// Typed client for the kim_qa.server API.
import type { OverlayPayload, Range } from './lib';

export type ShiftEvent = { t_after: number; lr: number; si: number; ap: number };

export type CentroidInfo = { file: string; lr: number; si: number; ap: number };

// An offline-reprocessed trajectory (a nested kim-log* folder), overlaid on the
// primary online run and sharing its timebase, centroid offset and couch shifts.
export type OfflineOverlay = {
  label: string;    // legend label (e.g. "pdf480")
  folder: string;   // source folder name, shown as the metrics Source
  t: number[];
  lr: number[];
  si: number[];
  ap: number[];
  file_index: number[];
  gantry?: number[];
  offset?: number | null;  // saved per-overlay time offset (s); null = follow primary
};

export type ServerPayload = OverlayPayload & {
  file_index: number[];
  shift_events: ShiftEvent[];
  offset_origin: string;
  centroid: CentroidInfo;
  saved_x_range?: [number, number] | null;
  kim_offline?: OfflineOverlay[];
};

export type ManifestEntry = {
  id: string;
  kind: 'motion' | 'static';
  hex_file: string | null;
  centroid_file: string | null;
  has_frames: boolean;
  has_couch_shifts: boolean;
  saved_offset: number | null;
  saved_ranges: Range[];
  offset_origin: string | null;
  y_range: number | null;
  hex_override: string | null;
  error: string | null;
};

export type AppManifest = {
  session: string;
  traces: string[];
  experiments: ManifestEntry[];
};

export type AppConfig = { root: string; traces_root: string; vendor: 'Elekta' | 'Varian' };

export type StateBody = {
  offset: number;
  ranges: Range[];
  y_range?: number | null;
  hex_override?: string | null;
  offset_origin?: string;
  x_range?: [number, number] | null;
  offline_offsets?: Record<string, number> | null;
};

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${await r.text()}`);
  return r.json() as Promise<T>;
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${url}: ${await r.text()}`);
  return r.json() as Promise<T>;
}

const eid = (id: string) => encodeURIComponent(id);

export const fetchManifest = () => get<AppManifest>('/api/manifest');
export const fetchConfig = () => get<AppConfig>('/api/config');
export const postVendor = (vendor: 'Elekta' | 'Varian') =>
  post<AppConfig>('/api/config', { vendor });
export const fetchPayload = (id: string) =>
  get<ServerPayload>(`/api/experiments/${eid(id)}/payload`);
export const postState = (id: string, body: StateBody) =>
  post<Record<string, unknown>>(`/api/experiments/${eid(id)}/state`, body);
export const postSave = (id: string, body: StateBody & { png_base64: string }) =>
  post<{ overlay_png: string; summary: string }>(
    `/api/experiments/${eid(id)}/save`, body);
export const framesBase = (id: string) => `/api/experiments/${eid(id)}/frames`;
