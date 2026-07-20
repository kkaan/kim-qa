import json
from pathlib import Path

import numpy as np

from kim_qa.metrics import overlay_metrics_table, overlay_residuals
from kim_qa.server.config import ServerConfig
from kim_qa.server.discovery import discover_sessions
from kim_qa.server.state import (
    STATE_FILENAME, load_state, regenerate_summary, update_entry,
)
from tests.fixtures import make_motion_session, write_hex_trace

GOLDEN = Path(__file__).parent / "golden" / "overlay_metrics.json"


def sample_data():
    hex_t = np.arange(0.0, 30.0, 0.02)
    hex_si = 2.0 * np.sin(2 * np.pi * 0.2 * hex_t)
    hex_lr = 0.3 * np.cos(2 * np.pi * 0.1 * hex_t)
    hex_ap = 0.5 * np.sin(2 * np.pi * 0.15 * hex_t)
    kim_t = np.linspace(0.0, 20.0, 60)
    off = 4.0
    kim_lr = np.interp(kim_t + off, hex_t, hex_lr) + 0.1
    kim_si = np.interp(kim_t + off, hex_t, hex_si) - 0.2
    kim_ap = np.interp(kim_t + off, hex_t, hex_ap) + 0.05
    return kim_t, kim_lr, kim_si, kim_ap, hex_t, hex_lr, hex_si, hex_ap, off


def test_overlay_metrics_known_bias():
    kt, klr, ksi, kap, ht, hlr, hsi, hap, off = sample_data()
    res = overlay_residuals(kt, klr, ksi, kap, ht, hlr, hsi, hap, off, [])
    rows = {r["name"]: r for r in overlay_metrics_table(res)}
    assert np.isclose(rows["LR"]["mean"], 0.1, atol=1e-6)
    assert np.isclose(rows["SI"]["mean"], -0.2, atol=1e-6)
    assert rows["LR"]["std"] < 1e-6            # constant bias, ddof=1 std ~ 0
    assert rows["3D"]["mean"] > 0
    assert res.n == 60


def test_ranges_restrict_samples():
    kt, klr, ksi, kap, ht, hlr, hsi, hap, off = sample_data()
    res = overlay_residuals(kt, klr, ksi, kap, ht, hlr, hsi, hap, off,
                            [[4.0, 9.0]])
    assert 0 < res.n < 60
    assert np.isclose(res.total_dt, 5.0)


def test_export_golden():
    """Write the golden file consumed by webapp/src/metrics-golden.test.ts."""
    kt, klr, ksi, kap, ht, hlr, hsi, hap, off = sample_data()
    res = overlay_residuals(kt, klr, ksi, kap, ht, hlr, hsi, hap, off, [])
    rows = overlay_metrics_table(res)
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps({
        "kim": {"t": kt.tolist(), "lr": klr.tolist(), "si": ksi.tolist(),
                "ap": kap.tolist()},
        "hex": {"t": ht.tolist(), "lr": hlr.tolist(), "si": hsi.tolist(),
                "ap": hap.tolist()},
        "offset": off,
        "expected_rows": rows,
    }))
    assert GOLDEN.exists()


def test_state_roundtrip_preserves_unknown_keys(tmp_path):
    (tmp_path / STATE_FILENAME).write_text(json.dumps(
        {"old-session": {"offset": 1.0, "custom_key": "kept"}}))
    update_entry(tmp_path, "new-session",
                 {"offset": 2.5, "ranges": [[1, 2]], "y_range": 10})
    state = load_state(tmp_path)
    assert state["old-session"]["custom_key"] == "kept"
    assert state["new-session"]["offset"] == 2.5


def test_regenerate_summary(tmp_path):
    traces = tmp_path / "Motion traces"
    make_motion_session(tmp_path, traces)
    cfg = ServerConfig(root=tmp_path)
    sessions = discover_sessions(cfg)
    update_entry(tmp_path, "lung-typical,Test_1518",
                 {"offset": 3.0, "ranges": []})
    out = regenerate_summary(tmp_path, sessions, "Elekta")
    text = out.read_text(encoding="utf-8")
    assert "lung-typical,Test_1518" in text
    assert "| Axis | Mean (mm) |" in text
