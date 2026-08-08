import { useEffect, useMemo, useRef, useState } from 'react';
import Plotly from '../plotly';
import { Plot } from '../plotly';
import {
  computeResiduals, flatZeroHex, hexCurveFromPayload, interp, metricsTable, token,
  type Axes, type HexCurve, type Range,
} from '../lib';
import {
  ManifestEntry, ServerPayload, StateBody,
  fetchPayload, framesBase as framesBaseFor, postSave, postState,
} from '../api';
import { multiGapSquash } from '../squash';
import { asRecorded } from '../ghost';

const OFFSET_MIN = -30;
const OFFSET_MAX = 400;
const OFFSET_STEP = 0.05;
const OFFSET_NUDGES = [10, 1, 0.2];
const DEFAULT_Y_RANGE = 10;         // mm; spec: default +/-10 on all panels
const COMPRESS_MIN_GAP = 20;        // s
const COMPRESS_KEEP = 7;            // s
// A couch shift sits at the file boundary just before its dead-time gap (the
// resume point can precede the gap start by tens of ms), so match the nearest
// event within a few seconds of the band start rather than requiring exact
// coincidence.
const BAND_EVENT_TOL = 3;           // s

const PANELS = [
  { key: 'lr' as const, label: 'LR (mm)', suffix: '', domain: [0.7, 1.0] },
  { key: 'si' as const, label: 'SI (mm)', suffix: '2', domain: [0.36, 0.64] },
  { key: 'ap' as const, label: 'AP (mm)', suffix: '3', domain: [0.02, 0.3] },
];

const f3 = (x: number) => (Number.isFinite(x) ? (x >= 0 ? '+' : '') + x.toFixed(3) : '--');
const s3 = (x: number) => (Number.isFinite(x) ? x.toFixed(3) : '--');
const f1s = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}`;

// Times (in shifted plot coordinates) at which the trajectory-log gantry passes
// each `stepDeg` multiple. Linear-interpolated per sample segment; the single
// gantry wrap (e.g. -90 -> 270) is skipped so it does not register a crossing.
function gantryTicks(t: number[], g: number[], offset: number, stepDeg = 45) {
  const ticks: { t: number; g: number }[] = [];
  for (let i = 0; i < t.length - 1; i++) {
    const t0 = t[i];
    const t1 = t[i + 1];
    const g0 = g[i];
    const g1 = g[i + 1];
    if (![t0, t1, g0, g1].every(Number.isFinite)) continue;
    if (Math.abs(g1 - g0) > 180) continue; // gantry angle wrap, not a real crossing
    const lo = Math.min(g0, g1);
    const hi = Math.max(g0, g1);
    for (let k = Math.ceil(lo / stepDeg); k <= Math.floor(hi / stepDeg); k++) {
      const gv = k * stepDeg;
      const frac = g1 === g0 ? 0 : (gv - g0) / (g1 - g0);
      ticks.push({ t: t0 + frac * (t1 - t0) + offset, g: gv });
    }
  }
  ticks.sort((a, b) => a.t - b.t);
  return { vals: ticks.map((x) => x.t), text: ticks.map((x) => signedGantryLabel(x.g)) };
}

// Tick LABELS use the signed convention (-180, 180] so the scale reads
// continuously across the wrap (..., -45, -135, -180/180, 135, ...) instead of
// jumping to the log's raw 0-360 values (225, 180, ...). Display only: tick
// positions, data remapping, and hover still use the raw log gantry.
function signedGantryLabel(g: number): string {
  const s = ((g % 360) + 540) % 360 - 180; // maps to [-180, 180); +/-180 -> -180
  return s === -180 ? '-180/180' : String(s);
}

// One entry per KIM point (array index == kim.t index == hovered pointIndex).
// Produced by tools/export_debug_frames.py, served at /assets/<exp>/debug-images/index.json.
type FrameEntry = {
  i: number;
  file: string;
  frame: number;
  t: number;
  gantry: number;
  marker_x: number;
  marker_y: number;
  mx: number; // detected marker x within the crop
  my: number; // detected marker y within the crop
  missing?: boolean;
};

// The user-tunable view state, lifted into the parent App so it survives
// navigating away to another session and back (remount) without a Save.
export type ViewState = {
  offset: number;
  ranges: Range[];
  yRange: number | null;
  xRange: [number, number] | null;
  // Per-offline-overlay time offset (s), keyed by source folder. Absent folder
  // = follow the primary offset.
  offlineOffsets: Record<string, number>;
};

type Props = {
  entry: ManifestEntry;
  traces: string[];
  baselines: string[];
  onToast: (m: string) => void;
  onStateSaved: () => void;
  initialView?: ViewState;
  onViewChange: (id: string, view: ViewState) => void;
};

export default function KimOverlay({
  entry, traces, baselines, onToast, onStateSaved, initialView, onViewChange,
}: Props) {
  const experiment = entry.id;
  const framesBase = framesBaseFor(experiment);
  const height = 560;
  // The parent-remembered view for this session at mount time. In a ref so it
  // is applied once (after the payload loads) without re-running the fetch.
  const initialViewRef = useRef(initialView);

  const [payload, setPayload] = useState<ServerPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [ranges, setRanges] = useState<Range[]>([]);
  // Persisted time-axis zoom/pan in TRUE time (null = default view). Captured
  // from Plotly relayout events (inverted out of display-squash coords) and
  // forward-mapped back when applied to the axis range.
  const [xRange, setXRange] = useState<[number, number] | null>(null);
  const [errorMode, setErrorMode] = useState(false);
  const [showGhost, setShowGhost] = useState(false);
  // Offline overlays currently toggled ON via the legend, in click order. The
  // last entry drives the metrics card (its colour + source); [] = the primary
  // online trace. Resets on remount (session switch).
  const [toggledOn, setToggledOn] = useState<string[]>([]);
  // Independent time offset per offline overlay, keyed by source folder. An
  // absent folder follows the primary `offset`; set once the user nudges that
  // overlay's alignment. Persisted to state under "offline_offsets".
  const [offlineOffsets, setOfflineOffsets] = useState<Record<string, number>>({});
  const [yRange, setYRange] = useState<number | null>(
    entry.y_range ?? DEFAULT_Y_RANGE);
  const [hexOverride, setHexOverride] = useState<string | null>(entry.hex_override);
  const [testLog, setTestLog] = useState<string | null>(entry.test_log_override ?? null);
  const [gantryRemap, setGantryRemap] = useState<boolean>(entry.gantry_remap ?? false);
  const [frames, setFrames] = useState<FrameEntry[] | null>(null);
  const [cropSize, setCropSize] = useState(256);
  const [hoverFrame, setHoverFrame] = useState<FrameEntry | null>(null);
  const [tip, setTip] = useState<{ left: number; top: number; caret: number; below: boolean; lines: string[] } | null>(null);
  const [saving, setSaving] = useState(false);
  const plotWrapRef = useRef<HTMLDivElement>(null);
  const graphDivRef = useRef<HTMLElement | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPayload(experiment)
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
        const iv = initialViewRef.current;
        if (iv) {
          // Restore the view we were showing before navigating away — this
          // (not the disk value) is authoritative, so an un-saved pan/zoom
          // survives a round-trip through another session.
          setOffset(iv.offset);
          setRanges(iv.ranges);
          setYRange(iv.yRange);
          setXRange(iv.xRange);
          setOfflineOffsets(iv.offlineOffsets ?? {});
        } else {
          setOffset(data.saved_offset ?? 0);
          setRanges((data.saved_ranges ?? []).map((r) => [r[0], r[1]] as Range));
          setXRange(data.saved_x_range ?? null);
          // Seed each overlay's saved offset; a null (follow-primary) is left out.
          const seed: Record<string, number> = {};
          for (const ov of data.kim_offline ?? []) {
            if (ov.offset != null) seed[ov.folder] = ov.offset;
          }
          setOfflineOffsets(seed);
        }
        // Interrupt sessions show the shift-removed trace by default so each
        // couch step and its effect is visible; the toggle can still hide it.
        setShowGhost((data.shift_events?.length ?? 0) > 0);
      })
      .catch((e) => !cancelled && setError(String(e)));
    return () => { cancelled = true; };
  }, [experiment]);

  // Mirror the live view up to the parent so navigating away and back restores
  // it. Gated on payload so the pre-load defaults never clobber a remembered
  // view; writes to a parent ref, so this causes no extra renders.
  useEffect(() => {
    if (!payload) return;
    onViewChange(experiment, { offset, ranges, yRange, xRange, offlineOffsets });
  }, [offset, ranges, yRange, xRange, offlineOffsets, payload, experiment, onViewChange]);

  useEffect(() => {
    if (!entry.has_frames) { setFrames(null); return; }
    let cancelled = false;
    fetch(`${framesBase}/index.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((idx) => {
        if (cancelled) return;
        setFrames(idx.frames as FrameEntry[]);
        if (idx.crop?.size) setCropSize(idx.crop.size);
      })
      .catch(() => !cancelled && setFrames(null));
    return () => { cancelled = true; };
  }, [entry.has_frames, framesBase]);

  useEffect(() => () => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
  }, []);

  const colors = useMemo(
    () => ({
      cyan: token('--cyan', '#36A7E1'),
      green: token('--green', '#96C13E'),
      pink: token('--pink', '#E71D73'),
      purple: token('--purple', '#951880'),
      orange: token('--orange', '#FF9200'),
      orangeSoft: token('--orange-soft', '#FFB04A'),
      gray: token('--gray', '#797979'),
      line: token('--line', '#e3e3e3'),
      ink2: token('--ink-2', '#2a2a2a'),
      muted: token('--muted', '#6b6b6b'),
      mono: token('--font-mono', 'JetBrains Mono, monospace'),
    }),
    [],
  );

  // Ground truth: hexamotion trace or baseline KIM log for motion (the
  // payload's hex block carries either fixed dt or an explicit irregular t),
  // synthetic flat-zero for static.
  const hex: HexCurve | null = useMemo(() => {
    if (!payload) return null;
    if (payload.kind === 'motion' && payload.hex) {
      return hexCurveFromPayload(payload.hex);
    }
    return flatZeroHex(payload.kim);
  }, [payload]);
  const gtSource = payload?.hex?.source;
  const gtIsBaseline = gtSource?.type === 'baseline';
  const gtLegend = gtIsBaseline ? `Baseline (${gtSource!.name})` : 'Hex (input)';

  // Which trace the metrics card describes: the last-toggled-on offline overlay,
  // else the primary online run.
  const activeOverlay = toggledOn.length ? toggledOn[toggledOn.length - 1] : null;
  const overlayColor = (i: number) =>
    [colors.purple, colors.green, colors.pink][i % 3];

  // The Time-offset control retargets to the ACTIVE trace: the last-toggled-on
  // offline overlay (its own independent offset), else the primary online run.
  // An overlay with no stored offset follows the primary until the user nudges
  // it. Keeps one slider driving whichever trace the metrics card describes.
  const activeFolder = activeOverlay && payload
    ? (payload.kim_offline ?? []).find((o) => o.label === activeOverlay)?.folder ?? null
    : null;
  const activeOffset = activeFolder != null
    ? (offlineOffsets[activeFolder] ?? offset) : offset;
  const setActiveOffset = (next: number | ((o: number) => number)) => {
    if (activeFolder != null) {
      setOfflineOffsets((prev) => {
        const cur = prev[activeFolder] ?? offset;
        const val = typeof next === 'function' ? next(cur) : next;
        return { ...prev, [activeFolder]: val };
      });
    } else {
      setOffset(next);
    }
  };

  const metrics = useMemo(() => {
    if (!payload || !hex) return null;
    const overlays = payload.kim_offline ?? [];
    const oi = activeOverlay ? overlays.findIndex((o) => o.label === activeOverlay) : -1;
    const ov = oi >= 0 ? overlays[oi] : null;
    const src = ov ? { t: ov.t, lr: ov.lr, si: ov.si, ap: ov.ap } : payload.kim;
    // Residuals honour the active trace's own alignment, so an offline overlay's
    // metrics reflect its independent offset, not the primary run's.
    const effOffset = ov ? (offlineOffsets[ov.folder] ?? offset) : offset;
    const res = computeResiduals(src, hex, effOffset, ranges);
    return {
      rows: metricsTable(res), n: res.n, totalDt: res.totalDt,
      source: ov ? `${ov.folder} (offline)` : payload.id,
      color: ov ? overlayColor(oi) : colors.orange,
    };
  }, [payload, hex, offset, offlineOffsets, ranges, activeOverlay, colors]);

  // Display-only dead-time compression map, shared by the figure (forward: true
  // shifted time -> compressed display coordinate) and by drag-select handling
  // (inverse: display coordinate -> true shifted time). Kept in one place so the
  // two directions never drift apart.
  const squashInfo = useMemo(() => {
    if (!payload) return null;
    const kimX = payload.kim.t.map((t) => t + offset);
    return multiGapSquash(
      [...kimX].sort((a, b) => a - b), COMPRESS_MIN_GAP, COMPRESS_KEEP);
  }, [payload, offset]);

  // Default view: from just before the first KIM point to 5 s past the last —
  // the end of the last trajectory file when couch shifts split the
  // acquisition. The hex trace keeps drawing past this (hold-to-end); zoom
  // out to see it run to completion. Anchored to saved_offset (not the live
  // slider) so the value is stable across renders; combined with
  // layout.uirevision this sets the initial range while still letting the
  // user's own zoom and pan persist.
  const defaultXRange = useMemo<[number, number] | undefined>(() => {
    if (!payload || payload.kim.t.length === 0) return undefined;
    const off = payload.saved_offset ?? 0;
    let lo = Infinity, hi = -Infinity;
    for (const t of payload.kim.t) { if (t < lo) lo = t; if (t > hi) hi = t; }
    return [lo + off - 1, hi + off + 5];
  }, [payload]);

  const figure = useMemo(() => {
    if (!payload || !hex || !squashInfo) return null;
    const kim = payload.kim;
    const kimX = kim.t.map((t) => t + offset);

    // Display-only dead-time compression: every gap > COMPRESS_MIN_GAP in
    // shifted plot-time collapses to COMPRESS_KEEP seconds.
    const { map: squash, bands } = squashInfo;
    const kimXd = kimX.map(squash);

    // Offline overlays (nested kim-log* folders): same offset + squash as the
    // primary; each gets a palette colour and starts hidden (legendonly), shown
    // by toggling its legend entry.
    const offlineTraces = (payload.kim_offline ?? []).map((ov, oi) => ({
      ov, color: overlayColor(oi),
      xd: ov.t.map((t) => squash(t + (offlineOffsets[ov.folder] ?? offset))),
    }));

    // The hexamotion holds its final position once the trace file ends
    // (verified on Bluey interrupt data: hold-last fits the post-trace KIM
    // tail at 0.42 mm RMSE vs 4.3 mm for looping), so draw the line flat to
    // the end of the acquisition instead of stopping at the file end.
    // Metrics need no change: interp() clamps to the endpoints = same hold.
    const hexEndT = hex.t.length ? hex.t[hex.t.length - 1] : -Infinity;
    const kimTrueMax = kimX.length ? Math.max(...kimX) : -Infinity;
    const holdTo = Math.max(hexEndT, kimTrueMax + 5);
    const held = holdTo > hexEndT;
    const hexX = (held ? [...hex.t, holdTo] : hex.t).map(squash);
    const hexY = held
      ? {
          lr: [...hex.lr, hex.lr[hex.lr.length - 1]],
          si: [...hex.si, hex.si[hex.si.length - 1]],
          ap: [...hex.ap, hex.ap[hex.ap.length - 1]],
        }
      : hex;

    // Match each compressed band to its couch shift event. The event's resume
    // point (t_after) sits at the file boundary just before the dead-time gap,
    // so attach the nearest event within BAND_EVENT_TOL of the band start rather
    // than requiring exact coincidence (the gap can start tens of ms later).
    const events = payload.shift_events ?? [];
    const bandEvents = bands.map((b) => {
      let best: (typeof events)[number] | null = null;
      let bestDist = Infinity;
      for (const e of events) {
        const dist = Math.abs(squash(e.t_after + offset) - b.x0);
        if (dist < bestDist) { best = e; bestDist = dist; }
      }
      return best && bestDist <= BAND_EVENT_TOL ? best : null;
    });

    const gantryArr = kim.gantry && kim.gantry.length === kim.t.length
      ? kim.gantry : undefined;
    const gt = gantryArr ? gantryTicks(kim.t, gantryArr, offset) : null;
    if (gt) gt.vals = gt.vals.map(squash);

    // The persisted zoom (true time) wins over the computed default view; both
    // are forward-mapped into display-squash coordinates for the axis range.
    const dxr = xRange
      ? ([squash(xRange[0]), squash(xRange[1])] as [number, number])
      : defaultXRange
        ? ([squash(defaultXRange[0]), squash(defaultXRange[1])] as [number, number])
        : undefined;

    const cdata = kim.t.map((_, j) => [j, gantryArr ? gantryArr[j] : null, kimX[j]]);
    const kimHoverProps = { hoverinfo: 'none' as const };

    const data: any[] = [];
    if (gt && gt.vals.length && dxr) {
      data.push({
        xaxis: 'x4', yaxis: 'y', x: dxr, y: [0, 0], type: 'scatter',
        mode: 'markers', marker: { color: 'rgba(0,0,0,0)' },
        hoverinfo: 'skip', showlegend: false,
      });
    }

    // Orange primary = KIM as recorded (the quantity the metrics describe);
    // segment 0 falls back to the corrected values, where the two coincide.
    // Translucent grey = shift-removed counterfactual (where the target would
    // have been had the couch not moved). Hex stays the raw input trace.
    const recByAxis = events.length
      ? {
          lr: asRecorded(kim.lr, payload.file_index, events, 'lr')
            .map((v, j) => v ?? kim.lr[j]),
          si: asRecorded(kim.si, payload.file_index, events, 'si')
            .map((v, j) => v ?? kim.si[j]),
          ap: asRecorded(kim.ap, payload.file_index, events, 'ap')
            .map((v, j) => v ?? kim.ap[j]),
        }
      : null;

    for (let i = 0; i < PANELS.length; i++) {
      const { key, suffix } = PANELS[i];
      const ax = { xaxis: `x${suffix}`, yaxis: `y${suffix}` };
      const first = i === 0;
      if (errorMode) {
        const resid = kim[key].map((v, j) => v - interp(kimX[j], hex.t, hex[key]));
        data.push({
          ...ax, x: kimXd, y: resid, customdata: cdata, type: 'scatter',
          mode: 'markers', name: 'Error (KIM minus hex)', legendgroup: 'err',
          showlegend: first, marker: { color: colors.orange, size: 4 },
          ...kimHoverProps,
        });
      } else {
        data.push({
          ...ax, x: hexX, y: hexY[key], type: 'scatter', mode: 'lines',
          name: gtLegend, legendgroup: 'hex', showlegend: first,
          line: { color: colors.cyan, width: 1.4 }, hoverinfo: 'skip',
        });
        data.push({
          ...ax, x: kimXd, y: recByAxis ? recByAxis[key] : kim[key],
          customdata: cdata, type: 'scatter',
          mode: 'markers',
          name: recByAxis ? 'KIM (as recorded)' : 'KIM (shift-removed)',
          legendgroup: 'kim',
          showlegend: first, marker: { color: colors.orange, size: 4 },
          ...kimHoverProps,
        });
        if (showGhost && recByAxis) {
          data.push({
            ...ax, x: kimXd, y: kim[key], type: 'scatter',
            mode: 'markers', name: 'KIM (shift-removed)', legendgroup: 'ghost',
            showlegend: first,
            marker: { color: colors.gray, size: 4, opacity: 0.4 },
            hovertemplate: 'shift-removed: %{y:.3f} mm<extra></extra>',
          });
        }
        for (const { ov, color, xd } of offlineTraces) {
          data.push({
            ...ax, x: xd, y: ov[key], type: 'scatter', mode: 'markers',
            name: `KIM offline · ${ov.label}`, legendgroup: `ov-${ov.label}`,
            showlegend: first, visible: 'legendonly',
            marker: { color, size: 3 },
            hovertemplate: `${ov.label}: %{y:.3f} mm<extra></extra>`,
          });
        }
      }
    }

    const shapes: any[] = [];
    // Ranges are stored in true shifted time; forward-map through the squash so
    // the shading lands on the same compressed x the user dragged over.
    for (const [lo, hi] of ranges) {
      for (const { suffix } of PANELS) {
        shapes.push({
          type: 'rect', xref: `x${suffix}`, yref: `y${suffix} domain`,
          x0: squash(lo), x1: squash(hi), y0: 0, y1: 1, fillcolor: colors.orangeSoft,
          opacity: 0.18, line: { width: 0 }, layer: 'below',
        });
      }
    }
    for (const b of bands) {
      shapes.push({
        type: 'rect', xref: 'x', yref: 'paper', x0: b.x0, x1: b.x1,
        y0: 0, y1: 1, fillcolor: 'rgba(120,120,120,0.10)',
        line: { width: 0 }, layer: 'below',
      });
      for (const x of [b.x0, b.x1]) {
        shapes.push({
          type: 'line', xref: 'x', yref: 'paper', x0: x, x1: x, y0: 0, y1: 1,
          line: { color: colors.muted, width: 1, dash: 'dot' },
        });
      }
    }

    const annotations: any[] = [];
    bands.forEach((b, bi) => {
      const ev = bandEvents[bi];
      annotations.push({
        xref: 'x', yref: 'paper', x: (b.x0 + b.x1) / 2, y: 0.5,
        text: (ev
          ? [`couch repositioned at ${Math.round(b.x0)} s`,
             `${Math.round(b.removed)} s dead time compressed`]
          : [`${Math.round(b.removed)} s dead time compressed`]).join('<br>'),
        showarrow: false, textangle: 90, bgcolor: 'rgba(255,255,255,0.65)',
        font: { family: colors.mono, size: 12, color: colors.muted },
      });
      if (ev) {
        for (const { key, suffix } of PANELS) {
          annotations.push({
            xref: 'x', yref: `y${suffix} domain`,
            x: b.x1, xanchor: 'left', xshift: 5, y: 0.96, yanchor: 'top',
            text: `couch ${f1s(ev[key])} mm`,
            showarrow: false, bgcolor: 'rgba(255,255,255,0.7)',
            font: { family: colors.mono, size: 12, color: colors.ink2 },
          });
        }
      }
    });

    const layout: any = {
      height, margin: { l: 64, r: 14, t: 26, b: 46 },
      dragmode: 'select', hovermode: 'closest', selectdirection: 'h',
      uirevision: experiment,
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: '#ffffff',
      font: { family: colors.mono, size: 13, color: colors.ink2 },
      legend: { orientation: 'h', x: 0, y: 1.06, font: { size: 13 } },
      shapes, annotations,
    };
    for (let i = 0; i < PANELS.length; i++) {
      const { label, suffix, domain } = PANELS[i];
      const last = i === PANELS.length - 1;
      layout[`yaxis${suffix}`] = {
        domain,
        title: { text: errorMode ? label.replace(' (mm)', ' err (mm)') : label, font: { size: 13 } },
        gridcolor: colors.line, zeroline: true,
        zerolinecolor: colors.muted, zerolinewidth: 1,
        ...(yRange != null && !errorMode
          ? { range: [-yRange, yRange], autorange: false } : {}),
      };
      layout[`xaxis${suffix}`] = {
        anchor: `y${suffix}`,
        matches: suffix === '' ? undefined : 'x',
        showticklabels: last,
        title: last ? { text: 'Time (s)', font: { size: 13 } } : undefined,
        gridcolor: colors.line, zeroline: false,
        ...(suffix === '' && dxr ? { range: dxr, autorange: false } : {}),
      };
    }
    if (gt && gt.vals.length && dxr) {
      layout.xaxis4 = {
        overlaying: 'x', side: 'top', anchor: 'y', tickmode: 'array',
        tickvals: gt.vals, ticktext: gt.text, ticks: 'outside', showgrid: false,
        zeroline: false, range: dxr, autorange: false,
        title: { text: 'Gantry (deg)', font: { size: 13 } }, tickfont: { size: 12 },
      };
      layout.margin = { ...layout.margin, t: 64, b: 64 };
      layout.legend = { ...layout.legend, y: -0.16, yanchor: 'top' };
    }
    return { data, layout };
  }, [payload, hex, squashInfo, offset, offlineOffsets, ranges, errorMode,
      showGhost, yRange, colors, defaultXRange, xRange, experiment]);

  const config = useMemo(
    () => ({
      displaylogo: false,
      responsive: true,
      modeBarButtonsToRemove: ['lasso2d', 'autoScale2d'],
      toImageButtonOptions: { format: 'png', filename: experiment || 'kim-overlay', scale: 2 },
    }),
    [experiment],
  );

  const onSelected = (e: any) => {
    if (!e || !e.range) return;
    const xkey = Object.keys(e.range).find((k) => k.startsWith('x'));
    if (!xkey) return;
    const [a, b] = e.range[xkey];
    // Plotly reports the range in compressed display coordinates; invert the
    // squash so we persist true shifted time. computeResiduals and the Python
    // summary both read ranges as true time (ts = kim.t + offset), so storing
    // display coordinates would silently select the wrong samples across a gap.
    const invert = squashInfo ? squashInfo.invert : (x: number) => x;
    const lo = invert(Math.min(a, b));
    const hi = invert(Math.max(a, b));
    setRanges((prev) => [...prev, [lo, hi] as Range]);
  };

  // Persist time-axis zoom/pan. Plotly reports the range in compressed display
  // coordinates, so invert the squash to store true time (the same convention
  // as ranges and the saved offset); double-click autorange clears it back to
  // the default view.
  const onRelayout = (e: any) => {
    if (!e) return;
    // Time axis (x), stored in true time (inverted out of the display squash).
    // A full-reset (double-click) carries autorange for BOTH x and y, so handle
    // them independently rather than early-returning on the x reset.
    if (e['xaxis.autorange']) {
      setXRange(null);
    } else {
      const a = e['xaxis.range[0]'];
      const b = e['xaxis.range[1]'];
      if (a != null && b != null) {
        const invert = squashInfo ? squashInfo.invert : (x: number) => x;
        setXRange([invert(Number(a)), invert(Number(b))]);
      }
    }
    // Value axis (y): the widget models one symmetric +/- window shared by all
    // three panels, so a drag-zoom on ANY panel's y-axis is captured as that
    // half-range (largest magnitude of the dragged bounds). This is the only
    // path that records a mouse y-zoom into state, so without it the zoom is
    // neither saved nor carried across a session switch. Autorange clears it.
    for (const ax of ['yaxis', 'yaxis2', 'yaxis3']) {
      if (e[`${ax}.autorange`]) { setYRange(null); break; }
      const lo = e[`${ax}.range[0]`];
      const hi = e[`${ax}.range[1]`];
      if (lo != null && hi != null) {
        const half = Math.max(Math.abs(Number(lo)), Math.abs(Number(hi)));
        setYRange(Math.round(half * 100) / 100);
        break;
      }
    }
  };

  // Legend toggles drive which overlay's metrics show. We track the on-order so
  // the last-toggled-on overlay wins; turning one off falls back to the one
  // beneath it (or the primary run). Returning true keeps Plotly's own
  // show/hide behaviour.
  const overlayLabelOf = (e: any): string | null => {
    const grp = e?.data?.[e?.curveNumber]?.legendgroup as string | undefined;
    return grp && grp.startsWith('ov-') ? grp.slice(3) : null;
  };
  const onLegendClick = (e: any) => {
    const label = overlayLabelOf(e);
    if (label == null) return true;                 // primary/hex/ghost: ignore
    const vis = e.data[e.curveNumber].visible;
    const visibleNow = vis === true || vis === undefined;
    setToggledOn((prev) => {
      const without = prev.filter((l) => l !== label);
      return visibleNow ? without : [...without, label];
    });
    return true;
  };
  const onLegendDoubleClick = (e: any) => {
    // Plotly isolates the clicked trace; mirror that in the metrics selection.
    const label = overlayLabelOf(e);
    setToggledOn(label ? [label] : []);
    return true;
  };

  // Hover a KIM/error marker -> show the tooltip below the point and (when the
  // slide has frames) preview the kV frame behind it.
  const onPointHover = (e: any) => {
    if (!e?.points?.length) return;
    const pt = e.points.find((p: any) => p.customdata != null);
    if (!pt) return;
    const cd = pt.customdata;
    if (hideTimer.current) {
      clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
    // Custom tooltip: anchored to the point's pixel box, placed below it and
    // clamped inside the plot so it never clips at the right edge. Flips above
    // when there is no room below (bottom panel).
    if (pt.bbox) {
      // cd[2] is the true (uncompressed) time; fall back to pt.x when absent so
      // the label stays honest under display time-compression.
      const tx = Array.isArray(cd) && cd[2] != null ? Number(cd[2]) : pt.x;
      const lines = [`${tx.toFixed(2)} s, ${pt.y.toFixed(3)} mm`];
      const g = Array.isArray(cd) ? cd[1] : null;
      if (g != null) lines.push(`gantry ${Number(g).toFixed(1)} deg`);
      const w = plotWrapRef.current?.clientWidth ?? 0;
      const h = plotWrapRef.current?.clientHeight ?? 0;
      const halfTip = 78; // ~half the tooltip width, for edge clamping
      const tipH = lines.length > 1 ? 46 : 28;
      const cx = (pt.bbox.x0 + pt.bbox.x1) / 2;
      const left = w ? Math.max(halfTip + 2, Math.min(cx, w - halfTip - 2)) : cx;
      let top = pt.bbox.y1 + 9;
      let below = true;
      if (h && top + tipH > h) {
        top = pt.bbox.y0 - tipH - 9;
        below = false;
      }
      setTip({ left, top, caret: cx, below, lines });
    }
    // kV frame preview, only on slides that loaded frames.
    const idx = Array.isArray(cd) ? cd[0] : cd;
    if (frames && idx != null && idx >= 0 && idx < frames.length) {
      setHoverFrame(frames[idx]);
    }
  };

  // Brief delay so sweeping between adjacent points does not flicker the card/tip.
  const onPointUnhover = () => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      setHoverFrame(null);
      setTip(null);
    }, 120);
  };

  const resetToSaved = () => {
    if (!payload) return;
    // With an overlay active, "default" means: stop overriding it and follow the
    // primary run again. Otherwise reset the primary view to the saved values.
    if (activeFolder != null) {
      setOfflineOffsets((prev) => {
        const n = { ...prev };
        delete n[activeFolder];
        return n;
      });
      return;
    }
    setOffset(payload.saved_offset ?? 0);
    setRanges((payload.saved_ranges ?? []).map((r) => [r[0], r[1]] as Range));
    setXRange(payload.saved_x_range ?? null);
  };
  const defaultOffset = activeFolder != null ? offset : (payload?.saved_offset ?? 0);
  const offsetOrigin = activeFolder != null
    ? 'follows primary run' : (payload?.offset_origin ?? null);

  const stateBody = (): StateBody => ({
    offset, ranges, y_range: yRange, hex_override: hexOverride,
    offset_origin: 'manual', x_range: xRange, offline_offsets: offlineOffsets,
    test_log: testLog, gantry_remap: gantryRemap,
  });

  const saveAll = async () => {
    if (!graphDivRef.current) return;
    setSaving(true);
    try {
      const url = await Plotly.toImage(graphDivRef.current, {
        format: 'png', width: 1400, height, scale: 2,
      });
      const png_base64 = url.split(',')[1];
      await postSave(experiment, { ...stateBody(), png_base64 });
      onToast('Saved: overlay.png, state, summary.md');
      onStateSaved();
    } catch (e) {
      onToast(String(e));
    } finally {
      setSaving(false);
    }
  };

  const refreshFromServer = async (toast: string) => {
    const data = await fetchPayload(experiment);
    setPayload(data);
    setOffset(data.saved_offset ?? 0);
    setRanges((data.saved_ranges ?? []).map((r) => [r[0], r[1]] as Range));
    setXRange(data.saved_x_range ?? null);
    const seed: Record<string, number> = {};
    for (const ov of data.kim_offline ?? []) {
      if (ov.offset != null) seed[ov.folder] = ov.offset;
    }
    setOfflineOffsets(seed);
    setShowGhost((data.shift_events?.length ?? 0) > 0);
    onToast(toast.replace('{origin}', data.offset_origin ?? 'reloaded'));
    onStateSaved();
  };

  const changeTestLog = async (v: string) => {
    const next = v === '' ? null : v;
    setTestLog(next);
    try {
      await postState(experiment, { ...stateBody(), test_log: next });
      // Server dropped the stale offset (fit to the old trace); refetch.
      await refreshFromServer(next
        ? `Test trace: ${next} — {origin}.` : 'Test trace: auto — reloaded.');
    } catch (e) {
      onToast(String(e));
    }
  };

  const toggleGantryRemap = async () => {
    const next = !gantryRemap;
    setGantryRemap(next);
    try {
      await postState(experiment, { ...stateBody(), gantry_remap: next });
      // The server dropped the stale offset; the remapped (or raw) baseline
      // timebase arrives with the fresh payload.
      await refreshFromServer(next
        ? 'Baseline remapped onto the test timebase via gantry — {origin}.'
        : 'Gantry remap off — baseline back on its own timebase.');
    } catch (e) {
      onToast(String(e));
    }
  };

  const changeHexOverride = async (v: string) => {
    const next = v === '' ? null : v;
    setHexOverride(next);
    try {
      await postState(experiment, { ...stateBody(), hex_override: next });
      // The server dropped the stale offset and re-fit against the new
      // ground truth; pull the fresh payload so the overlay and offset update.
      await refreshFromServer(next
        ? `Ground truth override: ${next} — {origin}.`
        : 'Ground-truth override cleared — reloaded.');
    } catch (e) {
      onToast(String(e));
    }
  };

  // The default alignment: the payload's saved_offset. Shown under the slider so
  // the tuned value is always visible, and restored by the "Back to default" button.
  const fmtOffset = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)} s`;
  // Step the offset by a fixed amount, clamped to the slider range and rounded to
  // the slider grid so repeated presses do not accumulate float drift.
  const nudge = (d: number) =>
    setActiveOffset((o) => Math.min(OFFSET_MAX, Math.max(OFFSET_MIN, Math.round((o + d) * 100) / 100)));
  const stepLabel = (d: number) => {
    const a = Math.abs(d);
    const mag = a >= 1 ? `${a} s` : `${Math.round(a * 1000)} ms`;
    return `${d > 0 ? '+' : '-'}${mag}`;
  };

  const baseStyle = { fontFamily: 'var(--font-body)' as const };

  if (error) {
    return (
      <div style={{ ...baseStyle, padding: 24, fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--muted)' }}>
        Could not load {experiment}: {error}
      </div>
    );
  }
  if (!payload || !figure || !metrics) {
    return (
      <div style={{ ...baseStyle, padding: 24, fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--muted)' }}>
        Loading {experiment}...
      </div>
    );
  }

  return (
    <div style={{ ...baseStyle, position: 'relative', display: 'flex', flexDirection: 'column', width: '100%', gap: 12 }}>
      <div style={{ display: 'flex', gap: 24, alignItems: 'stretch' }}>
        <div ref={plotWrapRef} style={{ flex: 1, minWidth: 0, position: 'relative' }}>
          <Plot
            data={figure.data}
            layout={figure.layout}
            config={config}
            useResizeHandler
            style={{ width: '100%', height: `${height}px` }}
            onSelected={onSelected}
            onRelayout={onRelayout}
            onLegendClick={onLegendClick}
            onLegendDoubleClick={onLegendDoubleClick}
            onHover={onPointHover}
            onUnhover={onPointUnhover}
            onInitialized={(_f: any, gd: any) => { graphDivRef.current = gd; }}
            onUpdate={(_f: any, gd: any) => { graphDivRef.current = gd; }}
          />
          {tip && <PointTip tip={tip} colors={colors} />}
        </div>
        <div style={{ width: 340, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <MetricsPanel rows={metrics.rows} n={metrics.n} totalDt={metrics.totalDt} source={metrics.source} mono={colors.mono} color={metrics.color} heading={gtIsBaseline ? `Tracking error. KIM vs baseline ${gtSource!.name}` : 'Tracking error. KIM vs HexaMotion'} />
          {(entry.has_frames || frames) && (
            <FramePanel
              base={framesBase}
              frame={hoverFrame}
              size={cropSize}
              colors={colors}
              available={!!frames}
            />
          )}
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 18,
          flexWrap: 'wrap',
          fontFamily: 'var(--font-mono)',
          fontSize: 15,
          color: 'var(--ink-2)',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1, minWidth: 320 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ color: 'var(--muted)' }}>
              Time offset
              {activeFolder != null && (
                <span style={{ color: metrics.color, marginLeft: 6 }}>· {activeOverlay}</span>
              )}
            </span>
            <input
              type="range"
              min={OFFSET_MIN}
              max={OFFSET_MAX}
              step={OFFSET_STEP}
              value={activeOffset}
              onChange={(e) => setActiveOffset(Number(e.target.value))}
              style={{ flex: 1, accentColor: activeFolder != null ? metrics.color : 'var(--orange)' }}
            />
            <span style={{ width: 92, textAlign: 'right' }}>{fmtOffset(activeOffset)}</span>
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 13, color: 'var(--muted)' }}>
            <button
              type="button"
              onClick={resetToSaved}
              style={{ ...btnStyle, fontSize: 13, padding: '5px 10px' }}
            >
              Back to default
            </button>
            <span style={{ display: 'inline-flex', gap: 4 }}>
              {[...OFFSET_NUDGES.map((d) => -d), ...[...OFFSET_NUDGES].reverse()].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => nudge(d)}
                  title={`Shift offset by ${stepLabel(d)}`}
                  style={{ ...btnStyle, fontSize: 12, padding: '5px 8px' }}
                >
                  {stepLabel(d)}
                </button>
              ))}
            </span>
          </div>
          <div style={{ fontSize: 13, color: 'var(--muted)' }}>
            Default {fmtOffset(defaultOffset)}{offsetOrigin ? `, ${offsetOrigin}` : ''}
          </div>
        </div>
        <button type="button" onClick={() => setRanges([])} style={btnStyle}>
          Clear ranges
        </button>
        <button
          type="button"
          onClick={() => setErrorMode((v) => !v)}
          style={{ ...btnStyle, background: errorMode ? 'var(--orange)' : '#fff', color: errorMode ? '#fff' : 'var(--ink-2)' }}
        >
          {errorMode ? 'Show overlay' : 'Show error'}
        </button>
        {(payload.shift_events?.length ?? 0) > 0 && (
          <button type="button" onClick={() => setShowGhost((v) => !v)}
            style={{ ...btnStyle, background: showGhost ? 'var(--gray)' : '#fff', color: showGhost ? '#fff' : 'var(--ink-2)' }}>
            {showGhost ? 'Hide shift-removed' : 'Show shift-removed'}
          </button>
        )}
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--muted)', fontSize: 13 }}>
          y-range ±
          <input
            type="number" min={1} max={100} step={1}
            value={yRange ?? ''}
            placeholder="auto"
            onChange={(e) => setYRange(e.target.value === '' ? null : Number(e.target.value))}
            style={{ width: 64, fontFamily: 'var(--font-mono)', fontSize: 13, padding: '4px 6px', border: '1px solid var(--line)' }}
          /> mm
        </label>
        {(entry.test_logs?.length ?? 0) > 1 && (
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--muted)', fontSize: 13 }}>
            test trace
            <select value={testLog ?? ''} onChange={(e) => changeTestLog(e.target.value)}
              style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>
              <option value="">auto ({entry.test_log === '.' ? 'session folder' : entry.test_log})</option>
              {entry.test_logs.map((d) => (
                <option key={d} value={d}>{d === '.' ? '(session folder)' : d}</option>
              ))}
            </select>
          </label>
        )}
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--muted)', fontSize: 13 }}>
          ground truth
          <select value={hexOverride ?? ''} onChange={(e) => changeHexOverride(e.target.value)}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>
            <option value="">auto{entry.hex_file ? ` (${entry.hex_file})` : ' (none)'}</option>
            {traces.length > 0 && (
              <optgroup label="hexamotion traces">
                {traces.map((t) => <option key={t} value={t}>{t}</option>)}
              </optgroup>
            )}
            {baselines.length > 0 && (
              <optgroup label="baseline KIM logs">
                {baselines.map((b) => (
                  <option key={b} value={`baseline:${b}`}>{b}</option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
        {gtIsBaseline && payload.hex?.gantry && payload.kim.gantry && (
          <button type="button" onClick={toggleGantryRemap}
            title="Place the baseline on the test run's timebase via the shared gantry angle (same-fraction replays have processing-speed-warped time columns)"
            style={{
              ...btnStyle,
              background: gantryRemap ? 'var(--cyan)' : 'transparent',
              color: gantryRemap ? '#fff' : 'var(--muted)',
              border: '1px solid var(--line)',
            }}>
            {gantryRemap ? 'gantry remap: on' : 'gantry remap: off'}
          </button>
        )}
        <button type="button" onClick={saveAll} disabled={saving}
          style={{ ...btnStyle, background: 'var(--orange)', color: '#fff', opacity: saving ? 0.6 : 1 }}>
          {saving ? 'Saving...' : 'Save'}
        </button>
        <span style={{ color: 'var(--muted)' }}>
          {ranges.length === 0
            ? 'No ranges (full overlap). Drag on a panel to add one.'
            : 'Ranges: ' + ranges.map(([lo, hi]) => `${lo.toFixed(1)} to ${hi.toFixed(1)} s`).join(', ')}
        </span>
      </div>
    </div>
  );
}

// Subtle point tooltip placed below (or above, when clamped) the hovered marker.
// Replaces Plotly's native side-anchored label so it sits under the cursor and
// stays inside the plot at the right edge. A small caret points back at the point.
function PointTip({
  tip,
  colors,
}: {
  tip: { left: number; top: number; caret: number; below: boolean; lines: string[] };
  colors: { line: string; ink2: string; muted: string; mono: string };
}) {
  // Caret tracks the true point even when the card is clamped at an edge.
  const caretDx = Math.max(-60, Math.min(60, tip.caret - tip.left));
  const caretSide = tip.below
    ? { top: -4, borderTop: `1px solid ${colors.line}`, borderLeft: `1px solid ${colors.line}` }
    : { bottom: -4, borderBottom: `1px solid ${colors.line}`, borderRight: `1px solid ${colors.line}` };
  return (
    <div
      style={{
        position: 'absolute',
        left: tip.left,
        top: tip.top,
        transform: 'translateX(-50%)',
        background: 'var(--paper)',
        border: `1px solid ${colors.line}`,
        borderRadius: 6,
        padding: '5px 9px',
        font: `12px ${colors.mono}`,
        lineHeight: 1.35,
        color: colors.ink2,
        whiteSpace: 'nowrap',
        boxShadow: '0 2px 8px rgba(0,0,0,0.10)',
        pointerEvents: 'none',
        zIndex: 5,
      }}
    >
      {tip.lines.map((l, i) => (
        <div key={i} style={i === 0 ? undefined : { color: colors.muted }}>
          {l}
        </div>
      ))}
      <span
        style={{
          position: 'absolute',
          left: `calc(50% + ${caretDx}px)`,
          width: 8,
          height: 8,
          marginLeft: -4,
          background: 'var(--paper)',
          transform: 'rotate(45deg)',
          ...caretSide,
        }}
      />
    </div>
  );
}

// In-column kV frame preview, pinned in the blank space below the metrics panel
// so it stays put rather than floating over the plot. Always rendered (with a
// placeholder when nothing is hovered) so the square never shifts the layout.
function FramePanel({
  base,
  frame,
  size,
  colors,
  available,
}: {
  base: string;
  frame: FrameEntry | null;
  size: number;
  colors: { cyan: string; orange: string; muted: string; mono: string };
  // False when no kV frame index was found in the experiment folder yet. The
  // panel still renders (reserving its space) as a black "images unavailable"
  // placeholder, so dropping a debug-images set in later lights it up with no
  // slide change.
  available: boolean;
}) {
  const half = size / 2;
  return (
    <div
      data-frame-card=""
      style={{
        flex: 1,
        minHeight: 0,
        border: '1px solid var(--line)',
        background: '#000',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
        {!available ? (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
              padding: 16,
              color: 'var(--muted)',
              fontFamily: colors.mono,
              fontSize: 13,
            }}
          >
            Images unavailable
          </div>
        ) : !frame ? (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
              padding: 16,
              color: 'var(--muted)',
              fontFamily: colors.mono,
              fontSize: 13,
            }}
          >
            Hover a KIM point to preview its kV frame.
          </div>
        ) : frame.missing ? (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--muted)',
              fontFamily: colors.mono,
              fontSize: 13,
            }}
          >
            kV frame not available
          </div>
        ) : (
          <>
            <img
              src={`${base}/${frame.file}`}
              alt=""
              style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block', objectFit: 'fill' }}
            />
            <svg
              viewBox={`0 0 ${size} ${size}`}
              preserveAspectRatio="none"
              style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
            >
              <line x1={half} y1={0} x2={half} y2={size} stroke={colors.cyan} strokeWidth={0.7} opacity={0.85} />
              <line x1={0} y1={half} x2={size} y2={half} stroke={colors.cyan} strokeWidth={0.7} opacity={0.85} />
              <circle cx={frame.mx} cy={frame.my} r={4.5} fill="none" stroke={colors.orange} strokeWidth={1.4} />
              <circle cx={frame.mx} cy={frame.my} r={1} fill={colors.orange} />
            </svg>
          </>
        )}
      </div>
      <div
        style={{
          flexShrink: 0,
          height: 24,
          boxSizing: 'border-box',
          fontFamily: colors.mono,
          fontSize: 11,
          lineHeight: '12px',
          color: '#e8e8e8',
          padding: '6px 9px',
          borderTop: '1px solid rgba(255,255,255,0.12)',
          display: 'flex',
          gap: 12,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
        }}
      >
        {frame && !frame.missing && (
          <>
            <span style={{ opacity: 0.7 }}>frame {frame.frame}</span>
            <span style={{ opacity: 0.7 }}>gantry {frame.gantry.toFixed(1)} deg</span>
          </>
        )}
      </div>
    </div>
  );
}

const btnStyle = {
  fontFamily: 'var(--font-mono)',
  fontSize: 14,
  padding: '8px 14px',
  border: '1px solid var(--line)',
  background: '#fff',
  color: 'var(--ink-2)',
  cursor: 'pointer',
  borderRadius: 2,
} as const;

function MetricsPanel({
  rows,
  n,
  totalDt,
  source,
  mono,
  color,
  heading,
}: {
  rows: { name: string; mean: number; std: number; p5: number; p95: number }[];
  n: number;
  totalDt: number;
  source: string;
  mono: string;
  color: string;   // accent (left border + 3D label) = active trace's colour
  heading: string;
}) {
  return (
    <div
      style={{
        width: '100%',
        background: 'var(--paper-warm)',
        border: '1px solid var(--line)',
        borderLeft: `4px solid ${color}`,
        padding: '16px 18px',
        fontFamily: mono,
        fontSize: 14,
        color: 'var(--ink-2)',
      }}
    >
      <div style={{ color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 12, marginBottom: 6 }}>
        {heading}
      </div>
      <div style={{ fontSize: 12, color: 'var(--ink-2)', marginBottom: 14, wordBreak: 'break-all', lineHeight: 1.3 }}>
        <span style={{ color: 'var(--muted)' }}>Source </span>
        {source}
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ color: 'var(--muted)', textAlign: 'right' }}>
            <th style={{ textAlign: 'left', fontWeight: 'normal' }}>Axis</th>
            <th style={{ fontWeight: 'normal' }}>Mean</th>
            <th style={{ fontWeight: 'normal' }}>Std</th>
            <th style={{ fontWeight: 'normal' }}>p5</th>
            <th style={{ fontWeight: 'normal' }}>p95</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const meanFail = r.name !== '3D' && Math.abs(r.mean) > 1;
            const stdFail = r.name !== '3D' && r.std > 2;
            return (
              <tr key={r.name} style={{ textAlign: 'right' }}>
                <td style={{ textAlign: 'left', color: r.name === '3D' ? color : 'inherit' }}>{r.name}</td>
                <td style={meanFail ? { color: '#c0392b' } : undefined}>{f3(r.mean)}</td>
                <td style={stdFail ? { color: '#c0392b' } : undefined}>{s3(r.std)}</td>
                <td>{f3(r.p5)}</td>
                <td>{f3(r.p95)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 10 }}>
        n = {n} samples over {totalDt.toFixed(1)} s (mm)
      </div>
    </div>
  );
}
