"""Dynamic localization: align a KIM trajectory to a moving ground-truth trace."""
import numpy as np
from scipy.interpolate import interp1d

_AXES = (("lr", "meas_x", "x", "dev_x", "truth_x"),
         ("si", "meas_y", "y", "dev_y", "truth_y"),
         ("ap", "meas_z", "z", "dev_z", "truth_z"))

MEAN_TOL_MM = 1.0
STD_TOL_MM = 2.0


def align_trajectory_to_truth(kim_df, truth_df, time_offset=None, metric_range=None):
    """Align KIM to a moving ground truth and compute deviation metrics.

    kim_df:   DataFrame with time, meas_x, meas_y, meas_z (mm; x=LR, y=SI, z=AP).
    truth_df: DataFrame with time, x, y, z (mm).
    time_offset: seconds added to KIM time to align with truth. If None, an RMSE
        search over the SI axis (-50..50 s, 0.1 s steps) chooses it.
    metric_range: optional (t_start, t_end) on the offset KIM time axis; metrics
        use only frames within it (inclusive). If None, the full overlap is used.

    Returns (comp_df, metrics, time_offset):
      comp_df:  kim_df copy with shifted 'time', interpolated truth_x/y/z, and
                dev_x/y/z = meas - truth.
      metrics:  dict of mean_/std_/p5_/p95_ per lr/si/ap (floats), plus
                'pass' (bool), 'fails' (list[str]), 'frame_interval' (float).
    """
    kim_time = kim_df["time"].to_numpy()

    interp = {
        "x": interp1d(truth_df["time"], truth_df["x"], kind="linear", fill_value="extrapolate"),
        "y": interp1d(truth_df["time"], truth_df["y"], kind="linear", fill_value="extrapolate"),
        "z": interp1d(truth_df["time"], truth_df["z"], kind="linear", fill_value="extrapolate"),
    }

    if time_offset is None:
        meas_si = kim_df["meas_y"].to_numpy()
        best_rmse = float("inf")
        time_offset = 0.0
        for shift in np.arange(-50.0, 50.0, 0.1):
            rmse = np.sqrt(np.mean((meas_si - interp["y"](kim_time + shift)) ** 2))
            if rmse < best_rmse:
                best_rmse = rmse
                time_offset = float(shift)

    shifted = kim_time + time_offset
    comp = kim_df.copy()
    comp["time"] = shifted
    for _ax, meas_col, truth_src, dev_col, truth_col in _AXES:
        comp[truth_col] = interp[truth_src](shifted)
        comp[dev_col] = comp[meas_col] - comp[truth_col]

    if metric_range is not None:
        t0, t1 = metric_range
        sub = comp[(comp["time"] >= t0) & (comp["time"] <= t1)]
    else:
        sub = comp

    metrics = {}
    fails = []
    for ax, _meas_col, _truth_src, dev_col, _truth_col in _AXES:
        vals = sub[dev_col].to_numpy()
        mean = float(np.mean(vals))
        std = float(np.std(vals))
        metrics[f"mean_{ax}"] = mean
        metrics[f"std_{ax}"] = std
        metrics[f"p5_{ax}"] = float(np.percentile(vals, 5))
        metrics[f"p95_{ax}"] = float(np.percentile(vals, 95))
        if abs(mean) > MEAN_TOL_MM:
            fails.append(f"{ax.upper()} mean {mean:.2f}")
        if std > STD_TOL_MM:
            fails.append(f"{ax.upper()} std {std:.2f}")

    metrics["fails"] = fails
    metrics["pass"] = not fails
    metrics["frame_interval"] = (
        float(np.mean(np.diff(kim_time))) if len(kim_time) > 1 else 0.0
    )
    return comp, metrics, time_offset
