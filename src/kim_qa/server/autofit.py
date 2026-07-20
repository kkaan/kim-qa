"""Time-offset auto-fit: coarse-then-fine RMSE grid on one axis.

Port of tools/batch_overlay_pdf.find_si_offset (return_diag=True), generalised
to any axis. Candidate offsets must overlap at least
max(min_overlap, min_overlap_frac * len(kim_t)) samples so the search cannot
win on a sliver of edge overlap. confidence in [0, 1]: 1 = deep, sharp RMSE
well; near 0 = flat well (axis has too little structure to localise).
"""
import numpy as np


def find_axis_offset(kim_t, kim_axis, hex_t, hex_axis, coarse=0.5, fine=0.05,
                     min_overlap=50, min_overlap_frac=0.6):
    kim_t = np.asarray(kim_t, float)
    kim_axis = np.asarray(kim_axis, float)
    hex_t = np.asarray(hex_t, float)
    hex_axis = np.asarray(hex_axis, float)
    no_fit = {"confidence": 0.0, "min_rmse": float("nan"),
              "median_rmse": float("nan")}
    if len(kim_t) == 0 or len(hex_t) < 2:
        return 0.0, no_fit
    lo = hex_t[0] - kim_t[-1]
    hi = hex_t[-1] - kim_t[0]
    need = max(min_overlap, int(min_overlap_frac * len(kim_t)))

    def rmse(delta):
        ts = kim_t + delta
        m = (ts >= hex_t[0]) & (ts <= hex_t[-1])
        if m.sum() < need:
            return np.inf
        r = kim_axis[m] - np.interp(ts[m], hex_t, hex_axis)
        return float(np.sqrt(np.mean(r * r)))

    grid = np.arange(lo, hi, coarse)
    if len(grid) == 0:
        return 0.0, no_fit
    rms = np.array([rmse(d) for d in grid])
    if not np.isfinite(rms).any():
        return 0.0, no_fit
    c = grid[int(np.nanargmin(rms))]
    fgrid = np.arange(c - coarse, c + coarse, fine)
    frms = np.array([rmse(d) for d in fgrid])
    off = float(fgrid[int(np.nanargmin(frms))])

    finite = rms[np.isfinite(rms)]
    med = float(np.median(finite))
    mn = float(np.nanmin(rms))
    conf = 0.0 if med <= 0 else max(0.0, 1.0 - mn / med)
    return off, {"confidence": conf, "min_rmse": mn, "median_rmse": med}
