import numpy as np

from kim_qa.server.autofit import find_axis_offset


def test_recovers_known_offset():
    hex_t = np.arange(0.0, 60.0, 0.02)
    hex_si = 2.0 * np.sin(2 * np.pi * 0.2 * hex_t) + 0.3 * hex_t
    true_offset = 12.3
    u = np.linspace(15.0, 55.0, 400)
    kim_t = u - true_offset
    kim_si = np.interp(u, hex_t, hex_si)
    off, diag = find_axis_offset(kim_t, kim_si, hex_t, hex_si)
    assert abs(off - true_offset) < 0.06
    assert diag["confidence"] > 0.4


def test_flat_trace_low_confidence():
    hex_t = np.arange(0.0, 60.0, 0.02)
    hex_si = np.zeros_like(hex_t)
    kim_t = np.linspace(5.0, 50.0, 300)
    kim_si = np.zeros_like(kim_t)
    off, diag = find_axis_offset(kim_t, kim_si, hex_t, hex_si)
    assert diag["confidence"] < 0.4


def test_no_possible_overlap_returns_zero():
    off, diag = find_axis_offset(
        np.array([0.0, 1.0]), np.array([0.0, 1.0]),
        np.array([0.0, 0.02]), np.array([0.0, 0.0]),
    )
    assert off == 0.0 and diag["confidence"] == 0.0
