"""Parse HexaMotion / 6DoF-robot input motion traces into a time/x/y/z frame."""
import numpy as np
import pandas as pd


def _is_float(token):
    try:
        float(token)
        return True
    except ValueError:
        return False


def parse_hexamotion_trace(filepath, dt=0.020, signs=(1.0, 1.0, 1.0)):
    """Parse a HexaMotion motion trace (commanded trace or 6DoF-robot input).

    Two on-disk layouts are supported:
      * 3-column "trajectory" trace: an optional non-numeric header line
        (e.g. 'trajectory'), then X Y Z (mm) per row. No time column, so the
        time axis is reconstructed as row_index * dt.
      * >=4-column "_robot" trace: no header; col0 = time (s), col1/2/3 = X/Y/Z
        (mm), any trailing rotation columns ignored.

    signs = (s_lr, s_si, s_ap) multiplies X/Y/Z (default no flip). Values are
    otherwise passed through in mm. Returns a DataFrame with columns
    time, x, y, z (x=LR, y=SI, z=AP).

    Raises ValueError if the rows are not whitespace-separated numbers
    (e.g. a comma-delimited file) -- the ground-truth loader uses this to fall
    back to parse_robot_file.
    """
    with open(filepath, "r", encoding="utf-8") as fh:
        first = fh.readline().split()
    has_header = bool(first) and not _is_float(first[0])

    data = np.loadtxt(filepath, skiprows=1 if has_header else 0, ndmin=2)

    if data.shape[1] >= 4:
        time = data[:, 0]
        x, y, z = data[:, 1], data[:, 2], data[:, 3]
    else:
        time = np.arange(len(data)) * dt
        x, y, z = data[:, 0], data[:, 1], data[:, 2]

    return pd.DataFrame(
        {
            "time": time,
            "x": x * signs[0],
            "y": y * signs[1],
            "z": z * signs[2],
        }
    )
