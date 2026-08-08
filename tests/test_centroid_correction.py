"""Centroid file is required per session and its expected offset subtracted.

Covers: discovery error when no centroid file exists, session-local file
winning over a root-level one, root-level fallback, the expected-offset
subtraction in overlay payloads, and multi-marker KIM logs averaged into a
centroid trajectory.

Run:  uv run pytest tests/test_centroid_correction.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (  # noqa: E402
    make_static_session, write_centroid_file,
)
from kim_qa.io.marker_locations import read_kim_segments  # noqa: E402
from kim_qa.server.config import ServerConfig  # noqa: E402
from kim_qa.server.discovery import discover_sessions, find_centroid_file  # noqa: E402
from kim_qa.server.payloads import (  # noqa: E402
    build_overlay_payload, expected_centroid,
)

# seeds avg (2,4,6) cm - iso (1,1,1) cm = (1,3,5) cm -> *10, axis swap:
# expected LR(x)=+10, SI(y=Z)=+50, AP(z=-Y)=-30 mm.
SEEDS_2 = ((1.0, 2.0, 3.0), (3.0, 6.0, 9.0))
ISO = (1.0, 1.0, 1.0)
EXPECTED = {"lr": 10.0, "si": 50.0, "ap": -30.0}


def test_missing_centroid_falls_back_to_zero(tmp_path):
    make_static_session(tmp_path)
    (tmp_path / "Static,Test_1207" / "Phantom_Centroid.txt").unlink()
    sessions = discover_sessions(ServerConfig(root=tmp_path))
    assert len(sessions) == 1
    assert sessions[0].centroid_file is None
    assert sessions[0].error is None
    payload = build_overlay_payload(sessions[0], "Elekta", None)
    assert payload["centroid"] == {"file": None, "lr": 0.0, "si": 0.0, "ap": 0.0}
    # raw fixture values pass through unshifted
    assert abs(payload["kim"]["lr"][0] - (-0.02)) < 1e-6


def test_session_local_wins_over_root(tmp_path):
    sess = make_static_session(tmp_path)
    write_centroid_file(tmp_path / "Root_Centroid.txt", seeds=SEEDS_2, iso=ISO)
    found = find_centroid_file(sess, tmp_path)
    assert found == sess / "Phantom_Centroid.txt"


def test_root_level_fallback(tmp_path):
    sess = make_static_session(tmp_path)
    (sess / "Phantom_Centroid.txt").unlink()
    write_centroid_file(tmp_path / "PHANTOM_ROBOT_Centroid.txt")
    sessions = discover_sessions(ServerConfig(root=tmp_path))
    assert sessions[0].error is None
    assert sessions[0].centroid_file == tmp_path / "PHANTOM_ROBOT_Centroid.txt"


def test_expected_centroid_axes(tmp_path):
    sess = make_static_session(tmp_path)
    write_centroid_file(sess / "Phantom_Centroid.txt", seeds=SEEDS_2, iso=ISO)
    sessions = discover_sessions(ServerConfig(root=tmp_path))
    cent = expected_centroid(sessions[0])
    assert cent["file"] == "Phantom_Centroid.txt"
    for axis, want in EXPECTED.items():
        assert abs(cent[axis] - want) < 1e-9


def test_overlay_payload_subtracts_expected(tmp_path):
    sess_dir = make_static_session(tmp_path)
    write_centroid_file(sess_dir / "Phantom_Centroid.txt",
                        seeds=SEEDS_2, iso=ISO)
    sess = discover_sessions(ServerConfig(root=tmp_path))[0]
    payload = build_overlay_payload(sess, "Elekta", None)
    # fixture static session: lr = -0.02, si = +0.01, ap = +0.05 raw
    assert abs(payload["kim"]["lr"][0] - (-0.02 - EXPECTED["lr"])) < 1e-6
    assert abs(payload["kim"]["si"][0] - (0.01 - EXPECTED["si"])) < 1e-6
    assert abs(payload["kim"]["ap"][0] - (0.05 - EXPECTED["ap"])) < 1e-6
    assert payload["centroid"]["file"] == "Phantom_Centroid.txt"
    assert abs(payload["centroid"]["si"] - EXPECTED["si"]) < 1e-6


MULTI_HEADER = (
    "Frame No, Time (sec), Marker_0_AP, Marker_0_LR, Marker_0_SI, "
    "Marker_1_AP, Marker_1_LR, Marker_1_SI, "
    "Marker_2_AP, Marker_2_LR, Marker_2_SI, Filename\n"
)


def test_multi_marker_files_average(tmp_path):
    folder = tmp_path / "multi"
    folder.mkdir()
    lines = [MULTI_HEADER]
    for i in range(5):
        t = float(i)
        # marker APs 1/2/3 -> mean 2; LRs 10/20/30 -> 20; SIs 0.1/0.2/0.3 -> 0.2
        lines.append(
            f"{i}, {t:.3f}, 1.0, 10.0, 0.1, 2.0, 20.0, 0.2, 3.0, 30.0, 0.3, "
            f"frame_{i}, extra.tiff\n")
    (folder / "MarkerLocations_CouchShift_0.txt").write_text(
        "".join(lines), encoding="utf-8")
    segs = read_kim_segments(folder)
    assert segs["n_markers"] == 3
    assert np.allclose(segs["ap"], 2.0)
    assert np.allclose(segs["lr"], 20.0)
    assert np.allclose(segs["si"], 0.2)


def test_single_marker_real_header_uses_named_columns(tmp_path):
    """Real Bluey-style header: Marker_0 triple resolved by name."""
    folder = tmp_path / "single"
    folder.mkdir()
    header = ("Frame No, Time (sec), Marker_0_AP, Marker_0_LR, Marker_0_SI , "
              "Marker_0_X, Marker_0_Y, Filename\n")
    rows = [f"{i}, {float(i):.3f}, -1.2, -0.9, -1.0, 517, 388, "
            f"C:\\frames\\a,b.tiff\n" for i in range(3)]
    (folder / "MarkerLocations_CouchShift_0.txt").write_text(
        header + "".join(rows), encoding="utf-8")
    segs = read_kim_segments(folder)
    assert segs["n_markers"] == 1
    assert np.allclose(segs["ap"], -1.2)
    assert np.allclose(segs["lr"], -0.9)
    assert np.allclose(segs["si"], -1.0)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
