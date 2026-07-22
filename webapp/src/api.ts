// Typed client for the kim_qa.server API.
import type { CouchShiftPayload, OverlayPayload, Range } from './lib';

export type ShiftEvent = { t_after: number; lr: number; si: number; ap: number };

export type CentroidInfo = { file: string; lr: number; si: number; ap: number };

export type ServerPayload = OverlayPayload & {
  file_index: number[];
  shift_events: ShiftEvent[];
  offset_origin: string;
  centroid: CentroidInfo;
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
export const fetchCouchSteps = (id: string) =>
  get<CouchShiftPayload>(`/api/experiments/${eid(id)}/couch-steps`);
export const postState = (id: string, body: StateBody) =>
  post<Record<string, unknown>>(`/api/experiments/${eid(id)}/state`, body);
export const postSave = (id: string, body: StateBody & { png_base64: string }) =>
  post<{ overlay_png: string; summary: string }>(
    `/api/experiments/${eid(id)}/save`, body);
export const framesBase = (id: string) => `/api/experiments/${eid(id)}/frames`;
