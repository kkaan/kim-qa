"""Deviation + summary statistics for static localisation analysis."""
import numpy as np


def calculate_metrics(df, expected_centroid, time_interval=None):
    """
    Calculates deviations and metrics.
    df: DataFrame from parse_trajectory_file
    expected_centroid: dict from parse_centroid_file
    time_interval: tuple (start_time, end_time) or None
    """

    # Filter by time
    if time_interval:
        df = df[(df['time'] >= time_interval[0]) & (df['time'] <= time_interval[1])].copy()
    else:
        df = df.copy()

    # Calculate Deviations
    # Note: The MATLAB code subtracts the expected centroid from the measured centroid.
    # AND it seems to imply a coordinate swap for the EXPECTED centroid, but what about the MEASURED?
    # In readKIMData (MATLAB):
    # KIMData.xCent = (x1+x2+x3)/3 - Avg_marker_x;
    # KIMData.yCent = (y1+y2+y3)/3 - Avg_marker_y;
    # KIMData.zCent = (z1+z2+z3)/3 - Avg_marker_z;

    # So we must ensure Avg_marker_x/y/z matches the coordinate system of the measured data (LR, SI, AP).

    # In MATLAB:
    # Avg_marker_x = Avg_marker_x_iso; (Which was 10 * (SeedX - IsoX))
    # Avg_marker_y = Avg_marker_z_iso; (Which was 10 * (SeedZ - IsoZ))
    # Avg_marker_z = -Avg_marker_y_iso; (Which was -10 * (SeedY - IsoY))

    # This implies the Centroid File has a different coordinate system than the Trajectory File.
    # Centroid File: X, Y, Z
    # Trajectory File: LR, SI, AP

    # It looks like:
    # Traj LR (X) corresponds to Centroid X
    # Traj SI (Y) corresponds to Centroid Z ??
    # Traj AP (Z) corresponds to Centroid -Y ??

    # Let's apply this subtraction.

    df['dev_x'] = df['meas_x'] - expected_centroid['x']
    df['dev_y'] = df['meas_y'] - expected_centroid['y']
    df['dev_z'] = df['meas_z'] - expected_centroid['z']

    # Calculate Metrics
    metrics = {}
    for axis in ['x', 'y', 'z']:
        col = f'dev_{axis}'
        metrics[f'mean_{axis}'] = df[col].mean()
        metrics[f'std_{axis}'] = df[col].std()
        metrics[f'p5_{axis}'] = np.percentile(df[col], 5)
        metrics[f'p95_{axis}'] = np.percentile(df[col], 95)

    return df, metrics


class OverlayResiduals:
    """Residual arrays for the overlay view (KIM minus interpolated hex)."""

    def __init__(self, lr, si, ap, n, total_dt):
        self.lr, self.si, self.ap = lr, si, ap
        self.n, self.total_dt = n, total_dt


def overlay_residuals(kim_t, kim_lr, kim_si, kim_ap,
                      hex_t, hex_lr, hex_si, hex_ap,
                      offset, ranges):
    """KIM[i] - interp(kim_t[i] + offset, hex_t, hex_axis), restricted to the
    union of ranges (shifted time) or the full hex overlap when no ranges.

    Canonical Python twin of webapp/src/lib.ts computeResiduals; the numbers
    must match exactly (guarded by the golden-file vitest).
    """
    kim_t = np.asarray(kim_t, float)
    t_shifted = kim_t + float(offset)
    hex_t = np.asarray(hex_t, float)
    if ranges:
        mask = np.zeros_like(t_shifted, dtype=bool)
        for lo, hi in ranges:
            mask |= (t_shifted >= lo) & (t_shifted <= hi)
        total_dt = float(sum(hi - lo for lo, hi in ranges))
    else:
        mask = (t_shifted >= hex_t[0]) & (t_shifted <= hex_t[-1])
        total_dt = float(hex_t[-1] - hex_t[0])
    out = []
    for k, h in ((kim_lr, hex_lr), (kim_si, hex_si), (kim_ap, hex_ap)):
        interp = np.interp(t_shifted[mask], hex_t, np.asarray(h, float))
        out.append(np.asarray(k, float)[mask] - interp)
    return OverlayResiduals(out[0], out[1], out[2], int(mask.sum()), total_dt)


def overlay_metrics_table(res):
    """Per-axis (LR/SI/AP) + 3D Euclidean rows: mean, std (ddof=1), p5, p95."""
    rows = []
    for name, r in (("LR", res.lr), ("SI", res.si), ("AP", res.ap)):
        rows.append({"name": name,
                     "mean": float(np.mean(r)),
                     "std": float(np.std(r, ddof=1)),
                     "p5": float(np.percentile(r, 5)),
                     "p95": float(np.percentile(r, 95))})
    dist = np.sqrt(res.lr ** 2 + res.si ** 2 + res.ap ** 2)
    rows.append({"name": "3D",
                 "mean": float(np.mean(dist)),
                 "std": float(np.std(dist, ddof=1)),
                 "p5": float(np.percentile(dist, 5)),
                 "p95": float(np.percentile(dist, 95))})
    return rows
