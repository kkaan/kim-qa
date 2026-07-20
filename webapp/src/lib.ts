// Vendored from presentation-learn-phantom-update (kim-overlay); keep maths in sync.
// Shared data types and residual/metrics maths for the KIM overlay widgets.
// These are faithful TypeScript ports of the canonical implementations in
// KIM-QA-Analysis/tools/interactive_hex_kim_overlay.py (interp, compute_residuals,
// metrics_table) so the web view reproduces the desktop tool's numbers.

export type Axes = { t: number[]; lr: number[]; si: number[]; ap: number[]; gantry?: number[] };
export type Range = [number, number];

export type ExperimentKind = 'motion' | 'static' | 'couch_shift';

export type ManifestEntry = {
  id: string;
  kind: ExperimentKind;
  hex_file: string | null;
  saved_offset: number;
  saved_ranges: Range[];
  file: string;
};

export type Manifest = {
  session: string;
  generated_at: string;
  experiments: ManifestEntry[];
};

export type OverlayPayload = {
  id: string;
  kind: 'motion' | 'static';
  saved_offset: number;
  saved_ranges: Range[];
  kim: Axes;
  hex?: { dt: number; n: number; lr: number[]; si: number[]; ap: number[] };
};

export type CouchShiftPayload = {
  id: string;
  kind: 'couch_shift';
  saved_ranges: Range[];
  kim: Axes;
  file_index: number[];
  shifts: [number, number, number][];
  expected_steps: [number, number, number][];
  segment_bounds: Range[];
  shift_markers: number[];
};

export type HexCurve = { t: number[]; lr: number[]; si: number[]; ap: number[] };

/** numpy.interp: assumes xs ascending; clamps to endpoints outside the range. */
export function interp(x: number, xs: number[], ys: number[]): number {
  const n = xs.length;
  if (n === 0) return NaN;
  if (x <= xs[0]) return ys[0];
  if (x >= xs[n - 1]) return ys[n - 1];
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] <= x) lo = mid;
    else hi = mid;
  }
  const span = xs[hi] - xs[lo];
  if (span === 0) return ys[lo];
  return ys[lo] + ((x - xs[lo]) / span) * (ys[hi] - ys[lo]);
}

/** Unwrap a wrapping angle sequence (deg) into a continuous monotonic run, so a
 *  single 360 wrap in a gantry sweep does not break interpolation. */
export function unwrapDeg(g: number[]): number[] {
  if (g.length === 0) return [];
  const out = [g[0]];
  let off = 0;
  for (let i = 1; i < g.length; i++) {
    const d = g[i] - g[i - 1];
    if (d > 180) off -= 360;
    else if (d < -180) off += 360;
    out.push(g[i] + off);
  }
  return out;
}

/** Remap a query gantry sequence to the reference run's time, by interpolating
 *  ref time against ref gantry. Used to place offline trajectories (whose own time
 *  column is unreliable) onto the real-time run's time axis via the shared gantry
 *  angle. Assumes both runs sweep the gantry monotonically once and start at the
 *  same wrap phase (true for these arc acquisitions). */
export function remapGantryToTime(refGantry: number[], refT: number[], queryGantry: number[]): number[] {
  const gu = unwrapDeg(refGantry);
  // interp needs ascending xs; the sweep may be decreasing, so sort by unwrapped gantry.
  const order = gu.map((_, i) => i).sort((a, b) => gu[a] - gu[b]);
  const xs = order.map((i) => gu[i]);
  const ys = order.map((i) => refT[i]);
  return unwrapDeg(queryGantry).map((q) => interp(q, xs, ys));
}

export type Residuals = { lr: number[]; si: number[]; ap: number[]; n: number; totalDt: number };

/**
 * Residuals = KIM[i] - interp(kim_t[i] + offset, hex_t, hex_axis), restricted to
 * the union of selected ranges (in shifted time) or, when none are selected, to
 * the full hex overlap window. Mirrors compute_residuals().
 */
export function computeResiduals(
  kim: Axes,
  hex: HexCurve,
  offset: number,
  ranges: Range[],
): Residuals {
  const out: Residuals = { lr: [], si: [], ap: [], n: 0, totalDt: 0 };
  const lo0 = hex.t[0];
  const hi0 = hex.t[hex.t.length - 1];
  const useRanges = ranges.length > 0;
  out.totalDt = useRanges
    ? ranges.reduce((s, [lo, hi]) => s + (hi - lo), 0)
    : hi0 - lo0;

  for (let i = 0; i < kim.t.length; i++) {
    const ts = kim.t[i] + offset;
    const inWindow = useRanges
      ? ranges.some(([lo, hi]) => ts >= lo && ts <= hi)
      : ts >= lo0 && ts <= hi0;
    if (!inWindow) continue;
    out.lr.push(kim.lr[i] - interp(ts, hex.t, hex.lr));
    out.si.push(kim.si[i] - interp(ts, hex.t, hex.si));
    out.ap.push(kim.ap[i] - interp(ts, hex.t, hex.ap));
  }
  out.n = out.lr.length;
  return out;
}

function mean(a: number[]): number {
  if (a.length === 0) return NaN;
  let s = 0;
  for (const x of a) s += x;
  return s / a.length;
}

/** Sample standard deviation (ddof = 1), matching numpy.std(..., ddof=1). */
function stdSample(a: number[]): number {
  if (a.length < 2) return NaN;
  const m = mean(a);
  let s = 0;
  for (const x of a) s += (x - m) * (x - m);
  return Math.sqrt(s / (a.length - 1));
}

/** numpy.percentile with the default linear interpolation method. */
function percentile(a: number[], p: number): number {
  if (a.length === 0) return NaN;
  const s = [...a].sort((x, y) => x - y);
  if (s.length === 1) return s[0];
  const idx = (p / 100) * (s.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return s[lo];
  return s[lo] + (idx - lo) * (s[hi] - s[lo]);
}

export type MetricRow = { name: string; mean: number; std: number; p5: number; p95: number };

/** Per-axis (LR/SI/AP) plus 3D Euclidean magnitude. Mirrors metrics_table(). */
export function metricsTable(res: Residuals): MetricRow[] {
  const rows: MetricRow[] = [];
  const axes: [string, number[]][] = [
    ['LR', res.lr],
    ['SI', res.si],
    ['AP', res.ap],
  ];
  for (const [name, r] of axes) {
    rows.push({ name, mean: mean(r), std: stdSample(r), p5: percentile(r, 5), p95: percentile(r, 95) });
  }
  const dist = res.lr.map((_, i) => Math.sqrt(res.lr[i] ** 2 + res.si[i] ** 2 + res.ap[i] ** 2));
  rows.push({ name: '3D', mean: mean(dist), std: stdSample(dist), p5: percentile(dist, 5), p95: percentile(dist, 95) });
  return rows;
}

/** Read a CSS custom property off :root, with a hard-coded fallback. Plotly draws
 *  to canvas and does not resolve var() in its style attributes, so we resolve here. */
export function token(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/** Build a flat-zero hex curve spanning a kim time window (static experiments). */
export function flatZeroHex(kim: Axes): HexCurve {
  const lo = kim.t.length ? kim.t[0] - 1 : 0;
  const hi = kim.t.length ? kim.t[kim.t.length - 1] + 1 : 1e6;
  return { t: [lo, hi], lr: [0, 0], si: [0, 0], ap: [0, 0] };
}

/** Resolve a manifest-relative file path against the manifest URL's directory. */
export function resolveFile(manifestPath: string, file: string): string {
  const slash = manifestPath.lastIndexOf('/');
  const dir = slash >= 0 ? manifestPath.slice(0, slash) : '';
  return `${dir}/${file}`;
}
