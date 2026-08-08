"""Gantry-angle time remapping.

Same-fraction KIM logs (e.g. an RTF reprocessing vs its baseline acquisition)
share the gantry angle per frame, but their time columns are processing-speed
dependent — warped relative to each other, not just shifted. Remapping by the
shared gantry angle places one run on the other's timebase exactly.

Python twin of webapp/src/lib.ts remapGantryToTime/unwrapDeg; keep the two in
sync. Assumes both runs sweep the gantry monotonically once and start at the
same wrap phase (true for these arc acquisitions).
"""
import numpy as np


def remap_gantry_to_time(ref_gantry, ref_t, query_gantry) -> np.ndarray:
    """Time on the REFERENCE run's timebase at which it passed each QUERY
    frame's gantry angle. Angles in degrees (raw log values, may wrap)."""
    ref_gu = np.unwrap(np.asarray(ref_gantry, float), period=360.0)
    q_gu = np.unwrap(np.asarray(query_gantry, float), period=360.0)
    order = np.argsort(ref_gu, kind="stable")
    return np.interp(q_gu, ref_gu[order], np.asarray(ref_t, float)[order])
