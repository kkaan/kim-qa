"""align_trajectory_to_truth recovers a known time offset via RMSE search."""
import sys

import numpy as np
import pandas as pd

from kim_qa import align_trajectory_to_truth


def _truth(tmax=20.0, dt=0.02):
    t = np.arange(0.0, tmax, dt)
    # Non-periodic Gaussian bump in SI so the RMSE minimum is unique.
    y = np.exp(-((t - 10.0) ** 2) / 2.0)
    return pd.DataFrame({"time": t, "x": 0.1 * t, "y": y, "z": -0.05 * t})


def _kim_shifted(delay):
    # KIM clock lags truth by `delay`: physical truth time = kim_time + delay.
    kt = np.arange(1.0, 18.0, 0.1)
    phys = kt + delay
    return pd.DataFrame(
        {
            "time": kt,
            "meas_x": 0.1 * phys,
            "meas_y": np.exp(-((phys - 10.0) ** 2) / 2.0),
            "meas_z": -0.05 * phys,
        }
    )


def test_recovers_known_offset():
    kim = _kim_shifted(1.0)
    _, _, offset = align_trajectory_to_truth(kim, _truth(), time_offset=None)
    assert abs(offset - 1.0) < 0.15, offset


def test_metrics_near_zero_at_recovered_offset():
    kim = _kim_shifted(1.0)
    _, metrics, _ = align_trajectory_to_truth(kim, _truth(), time_offset=None)
    assert abs(metrics["mean_si"]) < 0.05, metrics["mean_si"]
    assert abs(metrics["mean_lr"]) < 0.05, metrics["mean_lr"]


def test_supplied_offset_used_verbatim():
    kim = _kim_shifted(1.0)
    _, _, offset = align_trajectory_to_truth(kim, _truth(), time_offset=2.5)
    assert offset == 2.5, offset


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
