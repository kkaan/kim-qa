import { useEffect, useMemo, useState } from 'react';
import { Plot } from '../plotly';
import { token, type CouchShiftPayload } from '../lib';
import { ManifestEntry, fetchCouchSteps } from '../api';

const PANELS = [
  { idx: 0, label: 'LR (mm)', suffix: '' },
  { idx: 1, label: 'SI (mm)', suffix: '2' },
  { idx: 2, label: 'AP (mm)', suffix: '3' },
];
const DOMAINS = [
  [0.7, 1.0],
  [0.36, 0.64],
  [0.02, 0.3],
];

const f2 = (x: number) => (x >= 0 ? '+' : '') + x.toFixed(2);

export default function CouchSteps({ entry }: { entry: ManifestEntry }) {
  const experiment = entry.id;
  const height = 560;

  const [payload, setPayload] = useState<CouchShiftPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCouchSteps(experiment)
      .then((data) => !cancelled && setPayload(data))
      .catch((e) => !cancelled && setError(String(e)));
    return () => { cancelled = true; };
  }, [experiment]);

  const colors = useMemo(
    () => ({
      cyan: token('--cyan', '#36A7E1'),
      orange: token('--orange', '#FF9200'),
      gray: token('--gray', '#797979'),
      line: token('--line', '#e3e3e3'),
      ink2: token('--ink-2', '#2a2a2a'),
      muted: token('--muted', '#6b6b6b'),
      mono: token('--font-mono', 'JetBrains Mono, monospace'),
    }),
    [],
  );

  const figure = useMemo(() => {
    if (!payload) return null;
    const kim = payload.kim;
    const axisArrays: number[][] = [kim.lr, kim.si, kim.ap];

    const data: any[] = [];
    for (const { idx, suffix } of PANELS) {
      const ax = { xaxis: `x${suffix}`, yaxis: `y${suffix}` };
      const first = idx === 0;

      // Expected step level per segment, as one line trace broken between segments.
      const stepX: (number | null)[] = [];
      const stepY: (number | null)[] = [];
      for (let k = 0; k < payload.segment_bounds.length; k++) {
        const [lo, hi] = payload.segment_bounds[k];
        const yv = payload.expected_steps[k][idx];
        stepX.push(lo, hi, null);
        stepY.push(yv, yv, null);
      }
      data.push({
        ...ax,
        x: stepX,
        y: stepY,
        type: 'scatter',
        mode: 'lines',
        name: 'Expected (couch position)',
        legendgroup: 'exp',
        showlegend: first,
        line: { color: colors.cyan, width: 2.4 },
        connectgaps: false,
        hoverinfo: 'skip',
      });

      data.push({
        ...ax,
        x: kim.t,
        y: axisArrays[idx],
        type: 'scatter',
        mode: 'markers',
        name: 'KIM',
        legendgroup: 'kim',
        showlegend: first,
        marker: { color: colors.orange, size: 4 },
        hovertemplate: '%{x:.2f} s, %{y:.3f} mm<extra></extra>',
      });
    }

    // Vertical dashed lines at couch-move events, across every panel.
    const shapes: any[] = [];
    for (const x of payload.shift_markers) {
      for (const { suffix } of PANELS) {
        shapes.push({
          type: 'line',
          xref: `x${suffix}`,
          yref: `y${suffix} domain`,
          x0: x,
          x1: x,
          y0: 0,
          y1: 1,
          line: { color: colors.gray, dash: 'dash', width: 1 },
          layer: 'below',
        });
      }
    }

    const layout: any = {
      height,
      margin: { l: 64, r: 14, t: 26, b: 46 },
      dragmode: 'pan',
      hovermode: 'closest',
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: '#ffffff',
      font: { family: colors.mono, size: 13, color: colors.ink2 },
      legend: { orientation: 'h', x: 0, y: 1.06, font: { size: 13 } },
      shapes,
    };
    for (let i = 0; i < PANELS.length; i++) {
      const { label, suffix } = PANELS[i];
      const last = i === PANELS.length - 1;
      layout[`yaxis${suffix}`] = {
        domain: DOMAINS[i],
        title: { text: label, font: { size: 13 } },
        gridcolor: colors.line,
        zeroline: true,
        zerolinecolor: colors.muted,
        zerolinewidth: 1,
      };
      layout[`xaxis${suffix}`] = {
        anchor: `y${suffix}`,
        matches: suffix === '' ? undefined : 'x',
        showticklabels: last,
        title: last ? { text: 'Time (s), gaps compressed', font: { size: 13 } } : undefined,
        gridcolor: colors.line,
        zeroline: false,
      };
    }

    return { data, layout };
  }, [payload, colors, height]);

  const config = useMemo(
    () => ({
      displaylogo: false,
      responsive: true,
      modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
      toImageButtonOptions: { format: 'png', filename: experiment || 'kim-couch-shift', scale: 2 },
    }),
    [experiment],
  );

  const baseStyle = { fontFamily: 'var(--font-body)' as const };

  if (error) {
    return (
      <div style={{ ...baseStyle, padding: 24, fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--muted)' }}>
        Could not load {experiment}: {error}
      </div>
    );
  }
  if (!payload || !figure) {
    return (
      <div style={{ ...baseStyle, padding: 24, fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--muted)' }}>
        Loading {experiment}...
      </div>
    );
  }

  // Commanded couch displacement per segment, relative to the iso (segment 0) baseline.
  const base = payload.expected_steps[0];
  const seqRows = payload.expected_steps.map((s, k) => ({
    seg: k,
    lr: s[0] - base[0],
    si: s[1] - base[1],
    ap: s[2] - base[2],
  }));

  return (
    <div style={{ ...baseStyle, display: 'flex', gap: 24, width: '100%', alignItems: 'stretch' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <Plot
          data={figure.data}
          layout={figure.layout}
          config={config}
          useResizeHandler
          style={{ width: '100%', height: `${height}px` }}
        />
      </div>
      <div
        style={{
          width: 340,
          flexShrink: 0,
          background: 'var(--paper-warm)',
          border: '1px solid var(--line)',
          borderLeft: '4px solid var(--cyan)',
          padding: '16px 18px',
          fontFamily: colors.mono,
          fontSize: 14,
          color: 'var(--ink-2)',
        }}
      >
        <div style={{ color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 12, marginBottom: 6 }}>
          Commanded couch shift (mm)
        </div>
        <div style={{ fontSize: 12, color: 'var(--ink-2)', marginBottom: 14, wordBreak: 'break-all', lineHeight: 1.3 }}>
          <span style={{ color: 'var(--muted)' }}>Source </span>
          {payload.id.replace(/__couchshift$/, '')}
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ color: 'var(--muted)', textAlign: 'right' }}>
              <th style={{ textAlign: 'left', fontWeight: 'normal' }}>Seg</th>
              <th style={{ fontWeight: 'normal' }}>LR</th>
              <th style={{ fontWeight: 'normal' }}>SI</th>
              <th style={{ fontWeight: 'normal' }}>AP</th>
            </tr>
          </thead>
          <tbody>
            {seqRows.map((r) => (
              <tr key={r.seg} style={{ textAlign: 'right' }}>
                <td style={{ textAlign: 'left' }}>{r.seg === 0 ? 'iso' : r.seg}</td>
                <td>{f2(r.lr)}</td>
                <td>{f2(r.si)}</td>
                <td>{f2(r.ap)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 12, lineHeight: 1.5 }}>
          Cyan marks the expected marker position at each couch position. Dashed lines mark the
          couch moves: iso, shifted off iso, then back to iso.
        </div>
      </div>
    </div>
  );
}
