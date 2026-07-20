"""align_trajectory_to_truth metric values, range restriction, and pass/fail."""
import sys

import numpy as np
import pandas as pd

from kim_qa import align_trajectory_to_truth


def _zero_truth(tmax=30.0, dt=0.02):
    t = np.arange(0.0, tmax, dt)
    z = np.zeros_like(t)
    return pd.DataFrame({"time": t, "x": z, "y": z.copy(), "z": z.copy()})


def _kim(meas_x, meas_y=None, meas_z=None):
    n = len(meas_x)
    t = np.arange(0.0, float(n), 1.0)
    zeros = np.zeros(n)
    return pd.DataFrame(
        {
            "time": t,
            "meas_x": np.asarray(meas_x, dtype=float),
            "meas_y": zeros if meas_y is None else np.asarray(meas_y, dtype=float),
            "meas_z": zeros if meas_z is None else np.asarray(meas_z, dtype=float),
        }
    )


def test_metric_values_match():
    # truth=0 so dev == meas. LR const 0.5 (mean .5, std 0); SI alternates +/-3 (std>2).
    si = [3.0 if i % 2 == 0 else -3.0 for i in range(11)]
    kim = _kim([0.5] * 11, meas_y=si)
    _, m, off = align_trajectory_to_truth(kim, _zero_truth(), time_offset=0.0)
    assert off == 0.0
    assert abs(m["mean_lr"] - 0.5) < 1e-9, m["mean_lr"]
    assert abs(m["std_lr"]) < 1e-9, m["std_lr"]
    assert m["std_si"] > 2.0, m["std_si"]
    assert m["pass"] is False
    assert any("SI" in s for s in m["fails"]), m["fails"]


def test_metric_range_restricts():
    meas_x = [0.5] * 11
    meas_x[-1] = 100.0  # spike at t=10, outside the (0, 9) range
    kim = _kim(meas_x)
    _, m_full, _ = align_trajectory_to_truth(kim, _zero_truth(), time_offset=0.0)
    _, m_rng, _ = align_trajectory_to_truth(
        kim, _zero_truth(), time_offset=0.0, metric_range=(0.0, 9.0)
    )
    assert m_full["mean_lr"] > 9.0, m_full["mean_lr"]
    assert abs(m_rng["mean_lr"] - 0.5) < 1e-9, m_rng["mean_lr"]


def test_pass_within_thresholds():
    kim = _kim([0.9] * 11)
    _, m, _ = align_trajectory_to_truth(kim, _zero_truth(), time_offset=0.0)
    assert m["pass"] is True, m["fails"]


def test_fail_when_mean_exceeds():
    kim = _kim([1.5] * 11)
    _, m, _ = align_trajectory_to_truth(kim, _zero_truth(), time_offset=0.0)
    assert m["pass"] is False
    assert any("LR mean" in s for s in m["fails"]), m["fails"]


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL  {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
    sys.exit(1 if failures else 0)
