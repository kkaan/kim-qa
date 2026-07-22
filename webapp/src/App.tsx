import { useEffect, useState } from 'react';
import {
  AppConfig, AppManifest, ManifestEntry, fetchConfig, fetchManifest, postVendor,
} from './api';
import KimOverlay from './widgets/KimOverlay';
import CouchSteps from './widgets/CouchSteps';

const KIND_COLORS: Record<string, string> = {
  motion: 'var(--cyan)', static: 'var(--gray)',
};

export default function App() {
  const [manifest, setManifest] = useState<AppManifest | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<'overlay' | 'couch'>('overlay');
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  if (error) {
    return <div style={{ padding: 24, fontFamily: 'var(--font-mono)', color: 'var(--pink)' }}>{error}</div>;
  }
  if (!manifest || !config) {
    return <div style={{ padding: 24, fontFamily: 'var(--font-mono)', color: 'var(--muted)' }}>Loading...</div>;
  }

  const entry = manifest.experiments.find((e) => e.id === selected) ?? null;

  const changeVendor = async (v: 'Elekta' | 'Varian') => {
    try {
      setConfig(await postVendor(v));
      await reload();
      setToast(`Vendor set to ${v}. Couch-shift AP signs recomputed.`);
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
            onClick={() => { setSelected(e.id); setView('overlay'); }} />
        ))}
      </aside>

      {/* Main */}
      <main style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '20px 28px' }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--muted)',
          display: 'flex', gap: 16, alignItems: 'center',
        }}>
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
              {entry.hex_file ? `hex: ${entry.hex_file}` : 'flat-zero ground truth'}
              {entry.centroid_file ? ` · centroid: ${entry.centroid_file}` : ''}
              {entry.has_couch_shifts ? ' · couch shifts present' : ''}
            </div>
            {entry.has_couch_shifts && (
              <div style={{ marginBottom: 10, display: 'flex', gap: 6 }}>
                {(['overlay', 'couch'] as const).map((v) => (
                  <button key={v} type="button" onClick={() => setView(v)}
                    style={{
                      fontFamily: 'var(--font-mono)', fontSize: 13, padding: '6px 12px',
                      border: '1px solid var(--line)', cursor: 'pointer', borderRadius: 2,
                      background: view === v ? 'var(--orange)' : '#fff',
                      color: view === v ? '#fff' : 'var(--ink-2)',
                    }}>
                    {v === 'overlay' ? 'Overlay' : 'Couch steps'}
                  </button>
                ))}
              </div>
            )}
            {view === 'overlay'
              ? <KimOverlay key={entry.id} entry={entry} traces={manifest.traces}
                  onToast={setToast} onStateSaved={reload} />
              : <CouchSteps key={`${entry.id}-couch`} entry={entry} />}
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
