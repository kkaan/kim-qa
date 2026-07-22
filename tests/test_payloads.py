import numpy as np

from kim_qa.server.config import ServerConfig
from kim_qa.server.discovery import discover_sessions
from kim_qa.server.payloads import build_overlay_payload, read_hex
from tests.fixtures import (
    make_interrupt_session, make_motion_session, make_static_session,
    write_hex_trace,
)


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


def test_read_hex(tmp_path):
    path = tmp_path / "t.txt"
    write_hex_trace(path, n=100)
    h = read_hex(path)
    assert h["n"] == 100 and np.isclose(h["dt"], 0.02)
    assert len(h["si"]) == 100
