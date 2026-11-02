"""PRIME patient-export quirks in MarkerLocations(GA) logs.

Phantom exports never hit these; patient fractions do, and both corrupt the
data silently rather than raising, so they are covered here explicitly.
Reference implementation (and the original diagnosis) lives in
abstract-figures/make_prime_stepjump_figure.py.
"""
import numpy as np

from kim_qa.io.marker_locations import read_kim_segments
from tests.fixtures import GA_HEADER


def _write_rows(path, rows, header=True):
    """Write raw GA rows verbatim, so a test can express a malformed file."""
    text = (GA_HEADER if header else "") + "".join(r + "\n" for r in rows)
    path.write_text(text, encoding="utf-8")


def test_thousands_separator_in_time_column(tmp_path):
    """Past 1000 s KIM writes the Time field with a thousands separator
    ("1,028.870") into a comma-delimited file, so the row carries one extra
    field and every column after Time shifts right by one. Time AND all marker
    positions are corrupted, so it cannot be treated as a time-only problem.
    """
    sess = tmp_path / "thousands"
    sess.mkdir()
    _write_rows(sess / "MarkerLocationsGA_CouchShift_0.txt", [
        "0,  998.500, 89.60, -4.400, -19.000, 13.800, 491, 453, a.his",
        "2,  999.500, 89.61, -4.410, -19.010, 13.810, 491, 453, b.his",
        # The quirky row: Time is "1,000.500", giving 10 fields not 9.
        "4, 1,000.500, 89.62, -4.420, -19.020, 13.820, 491, 453, c.his",
        "6, 1,028.870, 89.63, -4.430, -19.030, 13.830, 491, 453, d.his",
    ])
    segs = read_kim_segments(sess)

    assert len(segs["t"]) == 4
    # Time recovered, not read as the bare "1".
    assert np.allclose(segs["t"], [998.5, 999.5, 1000.5, 1028.87])
    # Columns did not shift: AP/LR/SI still come from the marker fields.
    assert np.allclose(segs["ap"], [-4.40, -4.41, -4.42, -4.43])
    assert np.allclose(segs["lr"], [-19.00, -19.01, -19.02, -19.03])
    assert np.allclose(segs["si"], [13.80, 13.81, 13.82, 13.83])


def test_thousands_separator_leaves_normal_rows_untouched(tmp_path):
    """The repair must key on the Time field alone. A negative coordinate or a
    value that merely looks comma-adjacent must not be rewritten."""
    sess = tmp_path / "normal"
    sess.mkdir()
    _write_rows(sess / "MarkerLocationsGA_CouchShift_0.txt", [
        "0, 10.000, 89.60, -4.400, -19.000, 13.800, 491, 453, a.his",
        "2, 20.000, 89.61, -1.234, -19.010, 13.810, 491, 453, b.his",
    ])
    segs = read_kim_segments(sess)
    assert np.allclose(segs["t"], [10.0, 20.0])
    assert np.allclose(segs["ap"], [-4.400, -1.234])


def test_restarted_acquisition_yields_monotonic_time(tmp_path):
    """One CouchShift file can concatenate several kV acquisitions: the .his
    series restarts at 00001 and the clock is re-referenced, so the raw Time
    column jumps backwards (and can go negative). Downstream code takes the
    span from t[0]/t[-1], so a backwards jump silently drops samples from the
    metrics; the reader must hand back a monotonic timebase covering every
    sample.
    """
    sess = tmp_path / "restart"
    sess.mkdir()
    _write_rows(sess / "MarkerLocationsGA_CouchShift_0.txt", [
        "0, 100.000, 89.60, -4.400, -19.000, 13.800, 491, 453, 00205.a.his",
        "2, 100.500, 89.61, -4.410, -19.010, 13.810, 491, 453, 00206.a.his",
        # New acquisition: clock re-referenced, jumps backwards past zero.
        "4, -50.000, 89.62, -4.420, -19.020, 13.820, 491, 453, 00001.b.his",
        "6, -49.500, 89.63, -4.430, -19.030, 13.830, 491, 453, 00002.b.his",
    ])
    segs = read_kim_segments(sess)

    assert len(segs["t"]) == 4, "no sample may be dropped"
    t = segs["t"]
    assert np.all(np.diff(t) > 0), f"timebase must be monotonic, got {t}"
    # Within-acquisition spacing is real data and must be preserved exactly.
    assert np.isclose(t[1] - t[0], 0.5)
    assert np.isclose(t[3] - t[2], 0.5)
    # Positions are untouched by the re-basing.
    assert np.allclose(segs["ap"], [-4.40, -4.41, -4.42, -4.43])


def test_monotonic_time_is_left_alone(tmp_path):
    """A well-formed multi-file session keeps its real timebase, gap and all
    — the re-basing must not fire on the ordinary inter-file gap."""
    sess = tmp_path / "clean"
    sess.mkdir()
    _write_rows(sess / "MarkerLocationsGA_CouchShift_0.txt", [
        "0, 10.000, 89.60, -4.400, -19.000, 13.800, 491, 453, a.his",
        "2, 11.000, 89.61, -4.410, -19.010, 13.810, 491, 453, b.his",
    ])
    _write_rows(sess / "MarkerLocationsGA_CouchShift_1.txt", [
        "4, 90.000, 89.62, -4.420, -19.020, 13.820, 491, 453, c.his",
        "6, 91.000, 89.63, -4.430, -19.030, 13.830, 491, 453, d.his",
    ], header=False)
    segs = read_kim_segments(sess)
    assert np.allclose(segs["t"], [10.0, 11.0, 90.0, 91.0])
