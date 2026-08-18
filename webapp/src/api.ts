// Typed client for the kim_qa.server API.
import type { OverlayPayload, Range } from './lib';

export type ShiftEvent = { t_after: number; lr: number; si: number; ap: number };

export type CentroidInfo = { file: string | null; lr: number; si: number; ap: number };

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
  baseline: string | null;   // baseline KIM-log folder used as ground truth
  test_log: string;          // current primary log folder ("." = session folder)
  test_logs: string[];       // selectable candidates
  test_log_override: string | null;  // saved pick; null = auto
  gantry_remap: boolean;     // baseline GT remapped onto the test timebase
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
  baselines: string[];
  experiments: ManifestEntry[];
};

export type AppConfig = {
  root: string;
  traces_root: string;
  baselines_root: string;
  vendor: 'Elekta' | 'Varian';
  // Manual pick; null = auto-detect. Either a name/relative path under the
  // results root or an absolute path anywhere on disk.
  centroid_file: string | null;
  centroid_files: string[];       // *.txt directly under the results root
};

export type StateBody = {
  offset: number;
  ranges: Range[];
  y_range?: number | null;
  hex_override?: string | null;
  offset_origin?: string;
  x_range?: [number, number] | null;
  offline_offsets?: Record<string, number> | null;
  test_log?: string | null;
  gantry_remap?: boolean | null;
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
// "" selects auto-detection. Omitting `vendor` leaves it untouched. Rejects a
// path that does not exist or does not parse, so the caller must surface errors.
export const postCentroidFile = (centroid_file: string) =>
  post<AppConfig>('/api/config', { centroid_file });
// Opens a native file dialog on the machine running the server and returns the
// chosen path (null if cancelled). Saves nothing — post the path to apply it.
export const browseCentroidFile = () =>
  post<{ path: string | null }>('/api/browse/centroid', {});
export const fetchPayload = (id: string) =>
  get<ServerPayload>(`/api/experiments/${eid(id)}/payload`);
export const postState = (id: string, body: StateBody) =>
  post<Record<string, unknown>>(`/api/experiments/${eid(id)}/state`, body);
export const postSave = (id: string, body: StateBody & { png_base64: string }) =>
  post<{ overlay_png: string; summary: string }>(
    `/api/experiments/${eid(id)}/save`, body);
export const framesBase = (id: string) => `/api/experiments/${eid(id)}/frames`;
