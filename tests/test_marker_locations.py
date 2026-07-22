import numpy as np

from kim_qa.io.marker_locations import read_kim_segments, read_gantry_segments
from tests.fixtures import (
    make_interrupt_session, make_static_session, write_ga_file, write_kim_file,
)


def test_read_segments_concatenates_in_order(tmp_path):
    sess = make_interrupt_session(tmp_path)
    segs = read_kim_segments(sess)
    assert len(segs["t"]) == 20
    assert segs["file_index"].tolist() == [0] * 10 + [1] * 10
    # Raw timebase preserved (gap intact)
    assert segs["t"][10] - segs["t"][9] == 51.0
    # Positional columns survive the embedded-comma Filename field
    assert np.isclose(segs["ap"][0], -0.5)
    assert np.isclose(segs["lr"][0], 0.1)
    assert np.isclose(segs["si"][0], 0.0)


def test_single_segment(tmp_path):
    sess = make_static_session(tmp_path)
    segs = read_kim_segments(sess)
    assert len(segs["t"]) == 20
    assert set(segs["file_index"].tolist()) == {0}


def test_gantry_concatenated(tmp_path):
    sess = make_interrupt_session(tmp_path)
    g = read_gantry_segments(sess, expected_len=20)
    assert g is not None and len(g) == 20
    assert np.isclose(g[0], 180.0)
    assert np.isclose(g[10], 130.0)


def test_gantry_length_mismatch_returns_none(tmp_path):
    sess = make_interrupt_session(tmp_path)
    assert read_gantry_segments(sess, expected_len=99) is None


def test_gantry_absent_returns_none(tmp_path):
    sess = make_static_session(tmp_path)
    assert read_gantry_segments(sess, expected_len=20) is None


def test_ga_files_are_canonical_when_both_present(tmp_path):
    """Positions come from the GA files; the non-GA files are the fallback.
    Written with deliberately different values so the source is provable."""
    sess = tmp_path / "both"
    sess.mkdir()
    t = np.arange(0.0, 5.0, 1.0)
    write_kim_file(sess / "MarkerLocations_CouchShift_0.txt",
                   t, np.full(5, 9.0), np.full(5, 9.0), np.full(5, 9.0))
    write_ga_file(sess / "MarkerLocationsGA_CouchShift_0.txt",
                  t, np.full(5, 1.0), np.full(5, 2.0), np.full(5, 3.0),
                  np.linspace(180, 90, 5))
    segs = read_kim_segments(sess)
    assert np.allclose(segs["ap"], 1.0)
    assert np.allclose(segs["lr"], 2.0)
    assert np.allclose(segs["si"], 3.0)


def test_nonga_fallback_when_ga_absent(tmp_path):
    sess = tmp_path / "nonga"
    sess.mkdir()
    t = np.arange(0.0, 5.0, 1.0)
    write_kim_file(sess / "MarkerLocations_CouchShift_0.txt",
                   t, np.full(5, 1.5), np.full(5, 2.5), np.full(5, 3.5))
    segs = read_kim_segments(sess)
    assert np.allclose(segs["ap"], 1.5)
    assert np.allclose(segs["lr"], 2.5)
    assert np.allclose(segs["si"], 3.5)
