import numpy as np

from kim_qa.server.config import ServerConfig
from kim_qa.server.discovery import discover_sessions
from kim_qa.server.payloads import (
    build_manifest_entries, build_overlay_payload, read_hex,
)
from tests.fixtures import (
    make_baseline_pair, make_interrupt_session, make_motion_session,
    make_static_session, write_centroid_file, write_couch_shifts,
    write_ga_file, write_hex_trace,
)

BASELINE_OVERRIDES = {"2026-08-07-Pat03": "baseline:2026_06_17-pat03"}


def baseline_session(tmp_path, **pair_kw):
    make_baseline_pair(tmp_path, **pair_kw)
    cfg = ServerConfig(root=tmp_path)
    return {s.id: s for s in
            discover_sessions(cfg, BASELINE_OVERRIDES)}["2026-08-07-Pat03"]


def get_session(tmp_path, builder, **kw):
    builder(tmp_path, **kw)
    cfg = ServerConfig(root=tmp_path)
    return cfg, {s.id: s for s in discover_sessions(cfg)}


def test_interrupt_overlay_elekta(tmp_path):
    write_hex_trace(tmp_path / "Motion traces" / "t_Prostate_Continuous_Drift.txt")
    make_interrupt_session(tmp_path)
    cfg = ServerConfig(root=tmp_path)
    sess = {s.id: s for s in discover_sessions(cfg)}[
        "Prostate-Continuous-interrupt,Test_1350"]
    p = build_overlay_payload(sess, "Elekta", None)
    kim = p["kim"]
    # Raw timebase: the 51 s dead gap survives
    assert np.isclose(kim["t"][10] - kim["t"][9], 51.0)
    # Shift-removed: fixture built segment 1 raw = continuous + shift, so the
    # corrected trace is continuous (segment 1 first SI == 2.2, not 3.4)
    assert np.isclose(kim["si"][10], 2.2, atol=1e-6)
    assert np.isclose(kim["ap"][10], -0.5, atol=1e-6)
    # One shift event with Elekta signs, anchored to end of segment 0
    assert len(p["shift_events"]) == 1
    ev = p["shift_events"][0]
    assert np.isclose(ev["t_after"], 9.0)
    assert np.isclose(ev["ap"], 1.7) and np.isclose(ev["si"], 1.2) and np.isclose(ev["lr"], 0.3)
    assert p["file_index"] == [0] * 10 + [1] * 10
    assert p["kind"] == "motion" and "hex" in p
    assert len(p["kim"]["gantry"]) == 20


def test_interrupt_overlay_varian_flips_ap(tmp_path):
    write_hex_trace(tmp_path / "Motion traces" / "t_Prostate_Continuous_Drift.txt")
    make_interrupt_session(tmp_path)
    cfg = ServerConfig(root=tmp_path)
    sess = {s.id: s for s in discover_sessions(cfg)}[
        "Prostate-Continuous-interrupt,Test_1350"]
    p = build_overlay_payload(sess, "Varian", None)
    ev = p["shift_events"][0]
    assert np.isclose(ev["ap"], -1.7)          # AP sign flips
    assert np.isclose(ev["si"], 1.2)           # SI/LR identical
    # Correction direction flips with it: corrected = raw - cum
    assert np.isclose(p["kim"]["ap"][10], -0.5 + 1.7 + 1.7, atol=1e-6)


def test_static_payload(tmp_path):
    cfg, sessions = get_session(tmp_path, make_static_session)
    p = build_overlay_payload(sessions["Static,Test_1207"], "Elekta", None)
    assert p["kind"] == "static" and "hex" not in p
    assert p["saved_offset"] == 0.0 and p["offset_origin"] == "static"


def test_motion_autofit_and_state_priority(tmp_path):
    traces = tmp_path / "Motion traces"
    make_motion_session(tmp_path, traces)
    cfg = ServerConfig(root=tmp_path)
    sess = {s.id: s for s in discover_sessions(cfg)}["lung-typical,Test_1518"]
    p = build_overlay_payload(sess, "Elekta", None)
    # Fixture KIM sampled from the hex at +3 s; auto-fit should find ~3
    assert abs(p["saved_offset"] - 3.0) < 0.1
    assert p["offset_origin"].startswith("RMSE minimisation on SI")
    p2 = build_overlay_payload(sess, "Elekta",
                               {"offset": 7.5, "ranges": [[1, 2]],
                                "offset_origin": "manual"})
    assert p2["saved_offset"] == 7.5
    assert p2["saved_ranges"] == [[1.0, 2.0]]
    assert p2["offset_origin"] == "manual"


def test_baseline_gt_payload_shape_and_autofit(tmp_path):
    sess = baseline_session(tmp_path)
    p = build_overlay_payload(sess, "Elekta", None)
    assert p["kind"] == "motion"
    hx = p["hex"]
    assert "dt" not in hx
    assert hx["source"] == {"type": "baseline", "name": "2026_06_17-pat03"}
    assert hx["n"] == len(hx["t"]) == len(hx["si"]) == 160
    dt = np.diff(hx["t"])
    assert dt.min() < dt.max()                     # irregular timebase kept
    # Test log samples the shared waveform 0.5 s later -> autofit finds ~0.5
    assert abs(p["saved_offset"] - 0.5) < 0.1
    assert p["offset_origin"].startswith("RMSE minimisation on SI")
    assert p["centroid"]["file"] is None


def test_hexamotion_payload_shape_unchanged(tmp_path):
    traces = tmp_path / "Motion traces"
    make_motion_session(tmp_path, traces)
    sess = {s.id: s for s in discover_sessions(ServerConfig(root=tmp_path))}[
        "lung-typical,Test_1518"]
    p = build_overlay_payload(sess, "Elekta", None)
    assert set(p["hex"].keys()) == {"dt", "n", "lr", "si", "ap"}


def test_baseline_gt_gets_session_centroid_subtracted(tmp_path):
    # Root-level centroid: seeds avg (2,4,6) - iso (1,1,1) cm -> LR +10,
    # SI +50, AP -30 mm subtracted from BOTH kim and baseline GT.
    write_centroid_file(tmp_path / "Root_Centroid.txt",
                        seeds=((1.0, 2.0, 3.0), (3.0, 6.0, 9.0)),
                        iso=(1.0, 1.0, 1.0))
    sess = baseline_session(tmp_path)
    p = build_overlay_payload(sess, "Elekta", None)
    assert p["centroid"]["file"] == "Root_Centroid.txt"
    # Baseline waveform at its first sample (t=0): lr=0, si=0, ap=0
    assert abs(p["hex"]["lr"][0] - (0.0 - 10.0)) < 1e-3
    assert abs(p["hex"]["si"][0] - (0.0 - 50.0)) < 1e-3
    assert abs(p["hex"]["ap"][0] - (0.0 - (-30.0))) < 1e-3


def test_baseline_own_couch_shifts_applied(tmp_path):
    make_baseline_pair(tmp_path)
    b_dir = tmp_path / "Baselines" / "2026_06_17-pat03"
    # Second baseline segment offset by exactly one Elekta shift
    t1 = np.arange(30.0, 33.0, 1.0)
    write_ga_file(b_dir / "MarkerLocationsGA_CouchShift_1.txt",
                  t1, np.full(3, 1.7), np.full(3, 0.3), np.full(3, 1.2),
                  np.linspace(99, 95, 3), header=False)
    write_couch_shifts(b_dir / "couchShifts.txt",
                       [(-15.80, 125.50, -0.30), (-15.63, 125.62, -0.27)])
    sess = {s.id: s for s in discover_sessions(
        ServerConfig(root=tmp_path), BASELINE_OVERRIDES)}["2026-08-07-Pat03"]
    p = build_overlay_payload(sess, "Elekta", None)
    hx = p["hex"]
    assert hx["n"] == 163
    # Shift-removed: segment-1 values collapse back to zero
    assert abs(hx["si"][-1]) < 1e-6 and abs(hx["ap"][-1]) < 1e-6


def _make_warped_pair(tmp_path):
    """Baseline on true time; test log with 2x-compressed timestamps but the
    SAME gantry sweep and per-frame marker values (a same-fraction replay whose
    time column ran at double speed). A time shift cannot align them; the
    gantry remap can, exactly."""
    n = 120
    t_true = np.arange(n) * 0.2
    gantry = np.linspace(180.0, 100.0, n)
    lr, si, ap = (0.2 * np.sin(2 * np.pi * 0.1 * t_true),
                  2.0 * np.sin(2 * np.pi * 0.2 * t_true),
                  0.5 * np.sin(2 * np.pi * 0.15 * t_true))
    b_dir = tmp_path / "Baselines" / "2026_06_17-pat03"
    b_dir.mkdir(parents=True)
    write_ga_file(b_dir / "MarkerLocationsGA_CouchShift_0.txt",
                  t_true, ap, lr, si, gantry)
    s_dir = tmp_path / "2026-08-07-Pat03" / "log-version-124"
    s_dir.mkdir(parents=True)
    write_ga_file(s_dir / "MarkerLocationsGA_CouchShift_0.txt",
                  t_true * 0.5, ap, lr, si, gantry)   # warped timebase
    cfg = ServerConfig(root=tmp_path)
    return {s.id: s for s in
            discover_sessions(cfg, BASELINE_OVERRIDES)}["2026-08-07-Pat03"]


def test_baseline_hex_includes_gantry(tmp_path):
    sess = baseline_session(tmp_path)
    p = build_overlay_payload(sess, "Elekta", None)
    assert len(p["hex"]["gantry"]) == p["hex"]["n"]


def test_gantry_remap_aligns_warped_timebases(tmp_path):
    from kim_qa.metrics import overlay_residuals
    sess = _make_warped_pair(tmp_path)

    raw = build_overlay_payload(sess, "Elekta", {"offset": 0.0, "ranges": []})
    assert "remapped" not in raw["hex"]

    p = build_overlay_payload(sess, "Elekta", {"ranges": [],
                                               "gantry_remap": True})
    assert p["hex"]["remapped"] is True
    assert p["saved_offset"] == 0.0
    assert p["offset_origin"] == "gantry remap"
    # Remapped baseline now lives on the test log's timebase: residuals ~ 0
    hx = p["hex"]
    res = overlay_residuals(p["kim"]["t"], p["kim"]["lr"], p["kim"]["si"],
                            p["kim"]["ap"], hx["t"], hx["lr"], hx["si"],
                            hx["ap"], 0.0, [])
    assert res.n > 100
    assert abs(np.mean(res.si)) < 0.05 and float(np.std(res.si)) < 0.05
    # Without the remap the warped timebases disagree badly at offset 0
    res_raw = overlay_residuals(raw["kim"]["t"], raw["kim"]["lr"],
                                raw["kim"]["si"], raw["kim"]["ap"],
                                np.asarray(raw["hex"]["t"], float),
                                raw["hex"]["lr"], raw["hex"]["si"],
                                raw["hex"]["ap"], 0.0, [])
    assert float(np.std(res_raw.si)) > 0.5


def test_baseline_manifest_entry(tmp_path):
    sess = baseline_session(tmp_path)
    entry = build_manifest_entries([sess], {})[0]
    assert entry["baseline"] == "2026_06_17-pat03"
    assert entry["hex_file"] is None


def test_autofit_axis_is_data_driven(tmp_path):
    """The offset fit uses the ground truth's most active axis — no name
    matching. An LR-dominant trace fits on LR regardless of the session name."""
    traces = tmp_path / "Motion traces"
    traces.mkdir(parents=True)
    t_hex = np.arange(2500) * 0.02
    lr = 2.5 * np.sin(2 * np.pi * 0.2 * t_hex) + 0.1 * t_hex
    si = 0.2 * np.sin(2 * np.pi * 0.1 * t_hex)
    ap = 0.4 * np.sin(2 * np.pi * 0.15 * t_hex)
    lines = ["x\ty\tz\n"] + [f"{lr[i]:.4f}\t{si[i]:.4f}\t{ap[i]:.4f}\n"
                             for i in range(len(t_hex))]
    (traces / "lr_dominant.txt").write_text("".join(lines), encoding="utf-8")

    sess_dir = tmp_path / "some-unconventional-name_0001"
    sess_dir.mkdir()
    t = np.arange(120) * 0.25
    u = t + 2.0
    write_ga_file(sess_dir / "MarkerLocationsGA_CouchShift_0.txt",
                  t, 0.4 * np.sin(2 * np.pi * 0.15 * u),
                  2.5 * np.sin(2 * np.pi * 0.2 * u) + 0.1 * u,
                  0.2 * np.sin(2 * np.pi * 0.1 * u),
                  np.linspace(180.0, 100.0, len(t)))
    write_centroid_file(sess_dir / "Phantom_Centroid.txt")

    sess = {s.id: s for s in discover_sessions(
        ServerConfig(root=tmp_path),
        {"some-unconventional-name_0001": "lr_dominant.txt"})}[
        "some-unconventional-name_0001"]
    p = build_overlay_payload(sess, "Elekta", None)
    assert p["offset_origin"].endswith("RMSE minimisation on LR")
    assert abs(p["saved_offset"] - 2.0) < 0.1


def test_read_hex(tmp_path):
    path = tmp_path / "t.txt"
    write_hex_trace(path, n=100)
    h = read_hex(path)
    assert h["n"] == 100 and np.isclose(h["dt"], 0.02)
    assert "t" not in h                       # 3-col stays compact {dt, n}
    assert len(h["si"]) == 100


def test_read_hex_robot_whitespace_has_explicit_t(tmp_path):
    from tests.fixtures import write_robot_trace
    path = tmp_path / "Trace 1-Large AP motion.txt"
    write_robot_trace(path, n=50, t0=12.0)
    h = read_hex(path)
    assert h["n"] == 50 and "dt" not in h
    assert np.isclose(h["t"][0], 12.0)        # explicit time column kept
    assert np.isclose(h["t"][1] - h["t"][0], 0.04)
    assert len(h["ap"]) == 50


def test_read_hex_robot_comma_fallback(tmp_path):
    from tests.fixtures import write_robot_trace
    path = tmp_path / "robot.txt"
    write_robot_trace(path, n=40, comma=True, t0=3.0)
    h = read_hex(path)
    assert h["n"] == 40 and "t" in h
    assert np.isclose(h["t"][0], 3.0)
    assert np.isclose(h["si"][10],
                      2.5 * np.sin(2 * np.pi * 0.2 * (3.0 + 10 * 0.04)), atol=1e-3)


def test_read_hex_zero_based_constant_dt_robot_compacts(tmp_path):
    """A robot file whose time column is 0-based with a constant step
    compresses losslessly to the fixed-dt block."""
    from tests.fixtures import write_robot_trace
    path = tmp_path / "robot0.txt"
    write_robot_trace(path, n=40)
    h = read_hex(path)
    assert "t" not in h and np.isclose(h["dt"], 0.04)


def test_robot_trace_as_ground_truth_payload(tmp_path):
    """A robot file picked from the dropdown drives the overlay with its
    explicit timebase, end to end."""
    from tests.fixtures import write_robot_trace
    traces = tmp_path / "Motion traces"
    make_motion_session(tmp_path, traces)
    write_robot_trace(traces / "myrobot.txt", n=800, t0=5.0)
    sess = {s.id: s for s in discover_sessions(
        ServerConfig(root=tmp_path),
        {"lung-typical,Test_1518": "myrobot.txt"})}["lung-typical,Test_1518"]
    p = build_overlay_payload(sess, "Elekta", {"offset": 0.0, "ranges": []})
    assert p["kind"] == "motion"
    assert "t" in p["hex"] and p["hex"]["n"] == 800
