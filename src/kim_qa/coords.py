"""Shared coordinate transform between centroid-file and trajectory axes.

Centroid files use (X, Y, Z) in cm. The internal representation is (x, y, z)
in mm with the MATLAB Staticloc.m axis swap: x = X, y = Z, z = -Y.
"""
import numpy as np

CM_TO_MM = 10.0


def expected_centroid_from_iso(avg_marker, isocenter):
    """Marker centroid relative to isocenter, in mm, with the axis swap applied.

    avg_marker, isocenter: length-3 sequences (X, Y, Z) in cm.
    Returns {"x": X_iso, "y": Z_iso, "z": -Y_iso} in mm.
    """
    iso_rel = CM_TO_MM * (np.asarray(avg_marker, dtype=float)
                          - np.asarray(isocenter, dtype=float))
    return {"x": iso_rel[0], "y": iso_rel[2], "z": -iso_rel[1]}
