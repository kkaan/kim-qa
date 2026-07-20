import numpy as np

from kim_qa.io.marker_locations import read_kim_segments, read_gantry_segments
from tests.fixtures import make_interrupt_session, make_static_session


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
