import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AppConfig, AppManifest, CbctOffset, ManifestEntry, browseCentroidFile,
  fetchConfig, fetchManifest, postCbctOffset, postCentroidFile, postVendor,
} from './api';
import KimOverlay, { ViewState } from './widgets/KimOverlay';

const KIND_COLORS: Record<string, string> = {
  motion: 'var(--cyan)', static: 'var(--gray)',
};

// Sentinel <option> value for a centroid pick that is not a root-level file.
// "\0" cannot occur in a path, so it never collides with a real one.
const CUSTOM = '\0custom';

export default function App() {
  const [manifest, setManifest] = useState<AppManifest | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Per-session view state (offset/ranges/zoom), remembered across navigation.
  // A ref, not state: it is only read when an overlay mounts (which a session
  // switch already re-renders), so updates need not trigger a render.
  const viewStates = useRef<Record<string, ViewState>>({});
  const rememberView = useCallback((id: string, view: ViewState) => {
    viewStates.current[id] = view;
  }, []);

  const reload = () =>
    fetchManifest().then(setManifest).catch((e) => setError(String(e)));

  useEffect(() => {
    reload();
    fetchConfig().then(setConfig).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(id);
  }, [toast]);

  // Editable copy of the centroid path, so the field can be typed into without
  // firing a request per keystroke. Resynced whenever the server's value moves
  // (dropdown pick, Browse, or a rejected edit reverting).
  const [pathDraft, setPathDraft] = useState('');
  useEffect(() => { setPathDraft(config?.centroid_file ?? ''); },
    [config?.centroid_file]);

  if (error) {
    return <div style={{ padding: 24, fontFamily: 'var(--font-mono)', color: 'var(--pink)' }}>{error}</div>;
  }
  if (!manifest || !config) {
    return <div style={{ padding: 24, fontFamily: 'var(--font-mono)', color: 'var(--muted)' }}>Loading...</div>;
  }

  const entry = manifest.experiments.find((e) => e.id === selected) ?? null;
  const centroidIsCustom = !!config.centroid_file
    && !config.centroid_files.includes(config.centroid_file);

  const changeVendor = async (v: 'Elekta' | 'Varian') => {
    try {
      setConfig(await postVendor(v));
      await reload();
      setToast(`Vendor set to ${v}. Couch-shift AP signs recomputed.`);
    } catch (e) {
      setToast(String(e));
    }
  };

  // "" = auto-detect; anything else is a name under the root or a full path.
  // Applies to every session in the root, so reload the manifest to pick up
  // sessions whose centroid error has just cleared. The server rejects a path
  // that does not exist or does not parse — revert the field when it does.
  const changeCentroid = async (name: string) => {
    if (name === (config.centroid_file ?? '')) return;
    try {
      setConfig(await postCentroidFile(name));
      await reload();
      setToast(name ? `Centroid file set to ${name} for all sessions.`
        : 'Centroid file back to auto-detect.');
    } catch (e) {
      setToast(String(e));
      setPathDraft(config.centroid_file ?? '');
    }
  };

  // A setup error measured independently of KIM (typically on CBCT), typed in
  // mm per axis. The number entered is what was MEASURED, so the server adds
  // it to the expected centroid and thereby subtracts it from every KIM
  // trace. Root-wide, like the centroid pick, so it reloads the manifest.
  const changeCbct = async (axis: keyof CbctOffset, value: number) => {
    const next = { ...config.cbct_offset, [axis]: value };
    try {
      setConfig(await postCbctOffset(next));
      await reload();
      const any = next.lr || next.si || next.ap;
      setToast(any
        ? `CBCT detected offset: LR ${fmtMm(next.lr)}, SI ${fmtMm(next.si)}, `
          + `AP ${fmtMm(next.ap)} mm subtracted from KIM in every session.`
        : 'CBCT detected offset cleared.');
    } catch (e) {
      setToast(String(e));
    }
  };

  // Native dialog on the machine running the server (always this one — it
  // binds 127.0.0.1). Cancelling returns null and changes nothing.
  const browseCentroid = async () => {
    try {
      const { path } = await browseCentroidFile();
      if (path) await changeCentroid(path);
    } catch (e) {
      setToast(String(e));
    }
  };

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Sidebar */}
      <aside style={{
        width: 300, flexShrink: 0, overflowY: 'auto', background: 'var(--paper-warm)',
        borderRight: '1px solid var(--line)', padding: '18px 0',
      }}>
        <div style={{
          padding: '0 18px 12px', fontFamily: 'var(--font-mono)', fontSize: 12,
          color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em',
        }}>
          Sessions ({manifest.experiments.length})
        </div>
        {manifest.experiments.map((e) => (
          <SidebarRow key={e.id} entry={e} active={e.id === selected}
            onClick={() => setSelected(e.id)} />
        ))}
      </aside>

      {/* Main */}
      <main style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '20px 28px' }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--muted)',
          display: 'flex', flexDirection: 'column', gap: 7,
        }}>
          <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
            <span>QA · {manifest.session}</span>
            <label>
              vendor{' '}
              <select value={config.vendor}
                onChange={(ev) => changeVendor(ev.target.value as 'Elekta' | 'Varian')}>
                <option>Elekta</option>
                <option>Varian</option>
              </select>
            </label>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <label>
              centroid{' '}
              {/* Quick-pick of root-level files. A path chosen via Browse or
                  typed below lives outside this list, so it gets its own
                  entry — otherwise the select would snap back to auto. */}
              <select value={centroidIsCustom ? CUSTOM : (config.centroid_file ?? '')}
                onChange={(ev) => changeCentroid(ev.target.value === CUSTOM
                  ? (config.centroid_file ?? '') : ev.target.value)}>
                <option value="">(auto-detect)</option>
                {config.centroid_files.map((f) => (
                  <option key={f} value={f}>{f}</option>
                ))}
                {centroidIsCustom && <option value={CUSTOM}>(custom path)</option>}
              </select>
            </label>
            <button type="button" onClick={browseCentroid}
              title="Open a file dialog on this machine">
              Browse…
            </button>
            <input value={pathDraft} spellCheck={false}
              placeholder="or type a full path, then press Enter"
              title={pathDraft || undefined}
              onChange={(ev) => setPathDraft(ev.target.value)}
              onKeyDown={(ev) => {
                if (ev.key === 'Enter') changeCentroid(pathDraft.trim());
                if (ev.key === 'Escape') setPathDraft(config.centroid_file ?? '');
              }}
              onBlur={() => changeCentroid(pathDraft.trim())}
              style={{
                flex: 1, minWidth: 0, maxWidth: 560,
                fontFamily: 'var(--font-mono)', fontSize: 12,
                padding: '3px 6px', border: '1px solid var(--line)',
                borderRadius: 3, background: 'var(--paper)', color: 'var(--ink-2)',
              }} />
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span title="Setup error measured independently of KIM. Entered as
measured, so it is subtracted from every KIM trace and recorded in the report
as the CBCT detected offset.">
              CBCT detected offset (mm)
            </span>
            {(['lr', 'si', 'ap'] as const).map((ax) => (
              <CbctField key={ax} axis={ax} value={config.cbct_offset[ax]}
                onCommit={(v) => changeCbct(ax, v)} />
            ))}
            {(config.cbct_offset.lr || config.cbct_offset.si
              || config.cbct_offset.ap) ? (
              <span style={{ color: 'var(--orange)', fontSize: 12 }}>
                applied to all sessions
              </span>
            ) : null}
          </div>
        </div>

        {!entry ? (
          <p style={{ color: 'var(--muted)', fontFamily: 'var(--font-mono)', marginTop: 40 }}>
            Select a session from the sidebar.
          </p>
        ) : entry.error ? (
          <p style={{ color: 'var(--pink)', fontFamily: 'var(--font-mono)', marginTop: 40 }}>
            {entry.id}: {entry.error}
          </p>
        ) : (
          <>
            <h1 style={{
              fontFamily: 'var(--font-display)', fontSize: 34, margin: '10px 0 2px',
              fontWeight: 600,
            }}>
              <span style={{ color: 'var(--cyan)' }}>{entry.kind === 'motion' ? 'Motion' : 'Static'}</span>{' '}
              {entry.id}
            </h1>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--muted)', marginBottom: 10 }}>
              {entry.baseline ? `baseline: ${entry.baseline}`
                : entry.hex_file ? `hex: ${entry.hex_file}` : 'flat-zero ground truth'}
              {entry.centroid_file ? ` · centroid: ${entry.centroid_file}`
                : ' · no centroid — expected offset 0'}
              {entry.has_couch_shifts ? ' · couch shifts present' : ''}
            </div>
            {/* Key includes the vendor so a vendor switch remounts and refetches
                the open session with re-signed couch corrections, and the
                centroid pick, which shifts every trace by a new expected offset. */}
            <KimOverlay key={`${entry.id}:${config.vendor}:${config.centroid_file ?? ''}`
              + `:${config.cbct_offset.lr},${config.cbct_offset.si},${config.cbct_offset.ap}`}
              entry={entry} traces={manifest.traces}
              baselines={manifest.baselines ?? []}
              onToast={setToast} onStateSaved={reload}
              initialView={viewStates.current[entry.id]} onViewChange={rememberView} />
          </>
        )}

        {toast && (
          <div style={{
            position: 'fixed', bottom: 18, right: 18, background: 'var(--ink-2)',
            color: '#fff', padding: '10px 16px', borderRadius: 4,
            fontFamily: 'var(--font-mono)', fontSize: 13, zIndex: 10,
          }}>
            {toast}
          </div>
        )}
      </main>
    </div>
  );
}

// One decimal place, always signed, so +0.5 and -0.5 are never confusable.
const fmtMm = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}`;

// A per-axis mm field. Draft state so typing does not fire a request per
// keystroke (the same pattern as the centroid path field); commits on Enter
// or blur, reverts on Escape. Rounded to 1 dp on commit to match what the
// server stores, so the field can never disagree with the report.
function CbctField({ axis, value, onCommit }: {
  axis: 'lr' | 'si' | 'ap'; value: number; onCommit: (v: number) => void;
}) {
  const [draft, setDraft] = useState(value.toFixed(1));
  useEffect(() => { setDraft(value.toFixed(1)); }, [value]);
  const commit = () => {
    const v = Number(draft);
    // A half-typed "-" or "" reads as 0; anything unparseable reverts rather
    // than silently zeroing a real offset.
    if (draft.trim() === '') { onCommit(0); return; }
    if (!Number.isFinite(v)) { setDraft(value.toFixed(1)); return; }
    const rounded = Math.round(v * 10) / 10;
    if (rounded !== value) onCommit(rounded);
    else setDraft(value.toFixed(1));
  };
  return (
    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <span style={{ textTransform: 'uppercase' }}>{axis}</span>
      <input
        type="number" step={0.1} value={draft} spellCheck={false}
        aria-label={`CBCT detected offset ${axis.toUpperCase()} (mm)`}
        onChange={(ev) => setDraft(ev.target.value)}
        onKeyDown={(ev) => {
          if (ev.key === 'Enter') commit();
          if (ev.key === 'Escape') setDraft(value.toFixed(1));
        }}
        onBlur={commit}
        style={{
          width: 68, fontFamily: 'var(--font-mono)', fontSize: 12,
          padding: '3px 6px', border: '1px solid var(--line)',
          borderRadius: 3, background: 'var(--paper)',
          color: value ? 'var(--orange)' : 'var(--ink-2)',
        }} />
    </label>
  );
}

function SidebarRow({ entry, active, onClick }: {
  entry: ManifestEntry; active: boolean; onClick: () => void;
}) {
  const saved = entry.saved_offset != null;
  return (
    <div onClick={entry.error ? undefined : onClick}
      style={{
        padding: '9px 18px', cursor: entry.error ? 'default' : 'pointer',
        background: active ? 'var(--orange-tint)' : 'transparent',
        borderLeft: active ? '4px solid var(--orange)' : '4px solid transparent',
        opacity: entry.error ? 0.45 : 1,
      }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink-2)', wordBreak: 'break-all' }}>
        {entry.id} {saved && <span style={{ color: 'var(--green)' }}>✓</span>}
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: KIND_COLORS[entry.kind] }}>
        {entry.error ? `error: ${entry.error.slice(0, 60)}` :
          entry.kind + (entry.has_couch_shifts ? ' · interrupt' : '') +
          (entry.has_frames ? ' · kV' : '')}
      </div>
    </div>
  );
}
