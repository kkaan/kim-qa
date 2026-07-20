"""Synthetic session-folder builders shared by the server test modules."""
from pathlib import Path

import numpy as np

KIM_HEADER = (
    "Frame No, Time (sec), AP (mm), LR (mm), SI (mm), Gantry, "
    "Marker_0_X, Marker_0_Y, junk1, junk2, junk3, junk4, junk5, junk6, junk7, Filename\n"
)


def write_kim_file(path: Path, t, ap, lr, si, header=True, gantry=None,
                   filenames=None):
    """Write a MarkerLocations-style log. The Filename field contains an
    embedded comma (matching real files) so positional parsing is exercised."""
    lines = [KIM_HEADER] if header else []
    for i in range(len(t)):
        fname = (filenames[i] if filenames is not None
                 else f"frame_{i:04d}, extra.tiff")
        g = gantry[i] if gantry is not None else 180.0 - i
        lines.append(
            f"{i}, {t[i]:.3f}, {ap[i]:.3f}, {lr[i]:.3f}, {si[i]:.3f}, {g:.2f}, "
            f"512, 384, 0, 0, 0, 0, 0, 0, 0, {fname}\n"
        )
    path.write_text("".join(lines), encoding="utf-8")


# Real GA layout (verified against Bluey 2026-06-23 files): Gantry at index 2,
# marker mm columns at 3-5, pixel coords at 6-7, bare Filename (no comma) at 8.
GA_HEADER = (
    "Frame No, Time (sec), Gantry, Marker_0_AP, Marker_0_LR, Marker_0_SI, "
    "Marker_0_X, Marker_0_Y, Filename (of base frame in average framestack)\n"
)


def write_ga_file(path: Path, t, ap, lr, si, gantry, header=True,
                  filenames=None, marker_xy=(512, 384)):
    """GA variant: bare Filename (no comma), real column order (Gantry col 2)."""
    lines = [GA_HEADER] if header else []
    for i in range(len(t)):
        fname = filenames[i] if filenames is not None else f"Ch1_0_{i:04d}.tiff"
        lines.append(
            f"{i}, {t[i]:.3f}, {gantry[i]:.2f}, {ap[i]:.3f}, {lr[i]:.3f}, "
            f"{si[i]:.3f}, {marker_xy[0]}, {marker_xy[1]}, {fname}\n"
        )
    path.write_text("".join(lines), encoding="utf-8")


def write_couch_shifts(path: Path, rows_cm):
    """rows_cm: list of (vrt, lng, lat) in cm, one per couch position."""
    lines = ["VRT, LNG, LAT\n"]
    for vrt, lng, lat in rows_cm:
        lines.append(f"{vrt:.2f}, {lng:.2f}, {lat:.2f}\n")
    path.write_text("".join(lines), encoding="utf-8")


def make_interrupt_session(folder: Path, name="Prostate-Continuous-interrupt,Test_1350"):
    """Two-segment interrupt session with one couch shift.

    Segment 0: t 0..9 s (10 pts). Segment 1: t 60..69 s (10 pts), i.e. a 51 s
    dead-time gap. couchShifts has 2 rows -> 1 shift of
    (VRT +0.17, LNG +0.12, LAT +0.03) cm = Elekta AP +1.7, SI +1.2, LR +0.3 mm.
    Raw segment-1 values are offset by exactly that shift so the corrected
    (shift-removed) trace is continuous.
    """
    sess = folder / name
    sess.mkdir(parents=True, exist_ok=True)
    t0 = np.arange(0.0, 10.0, 1.0)
    t1 = np.arange(60.0, 70.0, 1.0)
    lr0, si0, ap0 = np.full(10, 0.1), np.linspace(0.0, 2.0, 10), np.full(10, -0.5)
    shift = {"lr": 0.3, "si": 1.2, "ap": 1.7}
    lr1 = np.full(10, 0.1) + shift["lr"]
    si1 = np.linspace(2.2, 4.0, 10) + shift["si"]
    ap1 = np.full(10, -0.5) + shift["ap"]
    write_kim_file(sess / "MarkerLocations_CouchShift_0.txt", t0, ap0, lr0, si0)
    write_kim_file(sess / "MarkerLocations_CouchShift_1.txt", t1, ap1, lr1, si1,
                   header=False)
    g0 = np.linspace(180.0, 135.0, 10)
    g1 = np.linspace(130.0, 90.0, 10)
    write_ga_file(sess / "MarkerLocationsGA_CouchShift_0.txt", t0, ap0, lr0, si0, g0)
    write_ga_file(sess / "MarkerLocationsGA_CouchShift_1.txt", t1, ap1, lr1, si1, g1,
                  header=False)
    write_couch_shifts(sess / "couchShifts.txt",
                       [(-15.80, 125.50, -0.30), (-15.63, 125.62, -0.27)])
    return sess


def write_hex_trace(path: Path, n=500, amp_si=2.0):
    """Tab-separated x y z trace, 20 ms per row (columns LR, SI, AP in mm)."""
    t = np.arange(n) * 0.02
    lr = 0.2 * np.sin(2 * np.pi * 0.1 * t)
    si = amp_si * np.sin(2 * np.pi * 0.2 * t) + 0.1 * t
    ap = 0.5 * np.sin(2 * np.pi * 0.15 * t)
    lines = ["x\ty\tz\n"]
    for i in range(n):
        lines.append(f"{lr[i]:.4f}\t{si[i]:.4f}\t{ap[i]:.4f}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def make_static_session(folder: Path, name="Static,Test_1207"):
    sess = folder / name
    sess.mkdir(parents=True, exist_ok=True)
    t = np.arange(0.0, 20.0, 1.0)
    z = np.zeros(20)
    write_kim_file(sess / "MarkerLocations_CouchShift_0.txt", t, z + 0.05, z - 0.02, z + 0.01)
    return sess


def make_motion_session(folder: Path, traces_root: Path,
                        name="lung-typical,Test_1518",
                        n_points=120, dt=0.25):
    """KIM sampled from the hex trace at a +3.0 s offset.

    Defaults give 120 points over 30 s: the auto-fit requires >= 50
    overlapping samples (min_overlap), so keep n_points >= 84 wherever the
    test exercises find_axis_offset. The hex trace is written 50 s long
    (n=2500) so the sampled window stays inside it.
    """
    sess = folder / name
    sess.mkdir(parents=True, exist_ok=True)
    t = np.arange(n_points) * dt
    u = t + 3.0
    si = 2.0 * np.sin(2 * np.pi * 0.2 * u) + 0.1 * u
    lr = 0.2 * np.sin(2 * np.pi * 0.1 * u)
    ap = 0.5 * np.sin(2 * np.pi * 0.15 * u)
    write_kim_file(sess / "MarkerLocations_CouchShift_0.txt", t, ap, lr, si)
    g = np.linspace(180.0, 100.0, len(t))
    write_ga_file(sess / "MarkerLocationsGA_CouchShift_0.txt", t, ap, lr, si, g)
    write_hex_trace(traces_root / "t_Lung_Typical.txt", n=2500)
    return sess
