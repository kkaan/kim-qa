"""remap_gantry_to_time: place a query trace on a reference run's timebase
via the shared gantry angle (Python twin of webapp/src/lib.ts
remapGantryToTime)."""
import numpy as np

from kim_qa.gantry import remap_gantry_to_time


def test_linear_warp_recovered():
    """Same sweep, query timebase 2x compressed: each query frame lands at the
    reference time with the same gantry angle."""
    ref_t = np.arange(100) * 0.2                 # real time
    gantry = np.linspace(180.0, 100.0, 100)      # shared sweep
    q_t = remap_gantry_to_time(gantry, ref_t, gantry[::2])
    assert np.allclose(q_t, ref_t[::2], atol=1e-9)


def test_wrap_through_360():
    """A sweep crossing the 0/360 wrap stays continuous after unwrapping."""
    ref_t = np.arange(50) * 0.5
    gantry = (np.linspace(20.0, -30.0, 50)) % 360.0   # 20 -> 350ish wrap
    q_t = remap_gantry_to_time(gantry, ref_t, gantry)
    assert np.allclose(q_t, ref_t, atol=1e-9)


def test_increasing_sweep():
    ref_t = np.arange(60) * 0.1
    gantry = np.linspace(100.0, 180.0, 60)
    q_t = remap_gantry_to_time(gantry, ref_t, gantry[10:20])
    assert np.allclose(q_t, ref_t[10:20], atol=1e-9)
