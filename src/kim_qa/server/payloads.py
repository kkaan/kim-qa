"""Assemble OverlayPayload JSON dicts from live files.

Overlay payloads keep the RAW timebase (no Python gap compression): display
compression is the widget's job, so a single slider offset aligns all
acquisition segments to a continuously-running hex trace.
"""
from pathlib import Path

import numpy as np

from kim_qa.io.centroid import parse_centroid_file
from kim_qa.io.couch import parse_couch_shifts
from kim_qa.interrupt import apply_couch_shifts
from kim_qa.io.marker_locations import read_kim_segments, read_gantry_segments
from .autofit import find_axis_offset
from .discovery import Session, align_axis_for

ROUND_DP = 4
CONFIDENCE_FLOOR = 0.4


def _r4(arr) -> list:
    return np.round(np.asarray(arr, dtype=float), ROUND_DP).tolist()


def read_hex(path: Path) -> dict:
    arr = np.genfromtxt(path, delimiter="\t", skip_header=1)
    return {
        "dt": 0.02,
        "n": int(len(arr)),
        "lr": _r4(arr[:, 0]),
        "si": _r4(arr[:, 1]),
        "ap": _r4(arr[:, 2]),
    }


def expected_centroid(session: Session) -> dict:
    """Per-axis expected marker-centroid offset from iso (mm, keys lr/si/ap)
    plus the source filename. Every session requires a centroid file; a
    phantom with the marker at isocentre uses an all-zero file."""
    if session.centroid_file is None:
        raise FileNotFoundError(f"{session.id}: no centroid file")
    exp = parse_centroid_file(session.centroid_file)["expected_centroid"]
    # parse_centroid_file axes map x->LR, y->SI, z->AP (see kim_qa.metrics).
    # "+ 0.0" normalises IEEE -0.0 so displays never show "-0.00".
    return {"file": session.centroid_file.name, "lr": float(exp["x"]) + 0.0,
            "si": float(exp["y"]) + 0.0, "ap": float(exp["z"]) + 0.0}


def load_session_arrays(session: Session, vendor: str) -> dict:
    """Raw-timebase stitched arrays, couch-shift-corrected (shift-removed)
    and centroid-corrected (expected marker offset from iso subtracted).

    Returns dict with numpy arrays t, lr, si, ap, file_index, optional gantry,
    shifts (list of vendor-signed {lr, si, ap} dicts, possibly empty), and
    centroid ({file, lr, si, ap} of the subtracted expected offset).
    """
    folder = session.kim_file.parent
    segs = read_kim_segments(folder)
    cent = expected_centroid(session)
    shifts = []
    lr = segs["lr"] - cent["lr"]
    si = segs["si"] - cent["si"]
    ap = segs["ap"] - cent["ap"]
    if session.has_couch_shifts:
        shifts = parse_couch_shifts(folder / "couchShifts.txt", vendor=vendor)
        lr, si, ap = apply_couch_shifts(lr, si, ap, segs["file_index"], shifts)
    gantry = read_gantry_segments(folder, expected_len=len(segs["t"]))
    return {"t": segs["t"], "lr": lr, "si": si, "ap": ap,
            "file_index": segs["file_index"], "gantry": gantry,
            "shifts": shifts, "centroid": cent}


def shift_events(t, file_index, shifts) -> list[dict]:
    """One event per segment transition: t_after = last time in the earlier
    segment, deltas = that transition's (vendor-signed) shift in mm."""
    events = []
    n_segs = int(file_index.max()) + 1 if len(file_index) else 1
    for k in range(1, n_segs):
        if k - 1 >= len(shifts):
            break
        sh = shifts[k - 1]
        t_after = float(np.max(t[file_index == k - 1]))
        events.append({"t_after": round(t_after, ROUND_DP),
                       "lr": round(float(sh["lr"]), ROUND_DP),
                       "si": round(float(sh["si"]), ROUND_DP),
                       "ap": round(float(sh["ap"]), ROUND_DP)})
    return events


def _resolve_offset(session: Session, arrays: dict, hex_data: dict | None,
                    state_entry: dict | None) -> tuple[float, str]:
    if state_entry is not None and "offset" in state_entry:
        return (float(state_entry["offset"]),
                str(state_entry.get("offset_origin", "saved")))
    if session.kind != "motion" or hex_data is None:
        return 0.0, "static"
    axis = align_axis_for(session.id)
    kim_axis = arrays[axis.lower()]
    hex_t = np.arange(hex_data["n"]) * hex_data["dt"]
    hex_axis = np.asarray(hex_data[axis.lower()])
    off, diag = find_axis_offset(arrays["t"], kim_axis, hex_t, hex_axis)
    if diag["confidence"] < CONFIDENCE_FLOOR:
        return off, f"low confidence, align manually (RMSE on {axis})"
    return off, f"RMSE minimisation on {axis}"


def build_overlay_payload(session: Session, vendor: str,
                          state_entry: dict | None) -> dict:
    arrays = load_session_arrays(session, vendor)
    hex_data = read_hex(session.hex_file) if (
        session.kind == "motion" and session.hex_file) else None
    offset, origin = _resolve_offset(session, arrays, hex_data, state_entry)
    ranges = [[float(lo), float(hi)]
              for lo, hi in (state_entry or {}).get("ranges", [])]
    kim = {"t": _r4(arrays["t"]), "lr": _r4(arrays["lr"]),
           "si": _r4(arrays["si"]), "ap": _r4(arrays["ap"])}
    if arrays["gantry"] is not None:
        kim["gantry"] = _r4(arrays["gantry"])
    payload = {
        "id": session.id,
        "kind": session.kind,
        "saved_offset": round(float(offset), ROUND_DP),
        "saved_ranges": ranges,
        "offset_origin": origin,
        "kim": kim,
        "file_index": [int(x) for x in arrays["file_index"]],
        "shift_events": shift_events(arrays["t"], arrays["file_index"],
                                     arrays["shifts"]),
        "centroid": {"file": arrays["centroid"]["file"],
                     **{k: round(arrays["centroid"][k], ROUND_DP)
                        for k in ("lr", "si", "ap")}},
    }
    if hex_data is not None:
        payload["hex"] = hex_data
    return payload
