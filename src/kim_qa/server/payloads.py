"""Assemble OverlayPayload / CouchShiftPayload JSON dicts from live files.

Overlay payloads keep the RAW timebase (no Python gap compression): display
compression is the widget's job, so a single slider offset aligns all
acquisition segments to a continuously-running hex trace. Couch-steps payloads
use the gap-compressed timebase (matching tools/export_overlay_to_webapp.py):
that view has no hex alignment.
"""
from pathlib import Path

import numpy as np

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


def load_session_arrays(session: Session, vendor: str) -> dict:
    """Raw-timebase stitched arrays, couch-shift-corrected (shift-removed).

    Returns dict with numpy arrays t, lr, si, ap, file_index, optional gantry,
    and shifts (list of vendor-signed {lr, si, ap} dicts, possibly empty).
    """
    folder = session.kim_file.parent
    segs = read_kim_segments(folder)
    shifts = []
    lr, si, ap = segs["lr"], segs["si"], segs["ap"]
    if session.has_couch_shifts:
        shifts = parse_couch_shifts(folder / "couchShifts.txt", vendor=vendor)
        lr, si, ap = apply_couch_shifts(lr, si, ap, segs["file_index"], shifts)
    gantry = read_gantry_segments(folder, expected_len=len(segs["t"]))
    return {"t": segs["t"], "lr": lr, "si": si, "ap": ap,
            "file_index": segs["file_index"], "gantry": gantry,
            "shifts": shifts}


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
    }
    if hex_data is not None:
        payload["hex"] = hex_data
    return payload


def compress_gaps(t_real, gap_threshold=5.0, compressed_gap=3.0):
    """Compress time gaps larger than gap_threshold to compressed_gap seconds.
    Returns (t_compressed, marker_positions). Port of the interactive tool."""
    t_real = np.asarray(t_real, dtype=float)
    n = len(t_real)
    if n == 0:
        return t_real.copy(), []
    t_out = np.empty(n)
    t_out[0] = t_real[0]
    for i in range(1, n):
        dt = t_real[i] - t_real[i - 1]
        t_out[i] = t_out[i - 1] + (compressed_gap if dt > gap_threshold else dt)
    t_out = t_out - t_out[0]
    markers = [float((t_out[i] + t_out[i - 1]) / 2.0)
               for i in range(1, n)
               if t_real[i] - t_real[i - 1] > gap_threshold]
    return t_out, markers


def build_couch_steps_payload(session: Session, vendor: str,
                              state_entry: dict | None) -> dict:
    """Uncorrected positions on a gap-compressed timebase + expected step
    levels per segment. Port of export_overlay_to_webapp.build_couch_shift."""
    folder = session.kim_file.parent
    couch = folder / "couchShifts.txt"
    if not couch.exists():
        raise ValueError(f"{session.id} has no couchShifts.txt")
    shifts = parse_couch_shifts(couch, vendor=vendor)
    segs = read_kim_segments(folder)
    t_disp, markers = compress_gaps(segs["t"])
    fi = segs["file_index"].astype(int)
    n_segs = int(fi.max()) + 1

    cum = np.zeros((n_segs, 3))                     # columns lr, si, ap
    for i, sh in enumerate(shifts[: n_segs - 1]):
        cum[i + 1] = cum[i] + np.array([sh["lr"], sh["si"], sh["ap"]])
    seg0 = fi == 0
    base = np.array([float(np.mean(segs["lr"][seg0])),
                     float(np.mean(segs["si"][seg0])),
                     float(np.mean(segs["ap"][seg0]))])
    expected = base + cum

    bounds = [[float(np.min(t_disp[fi == k])), float(np.max(t_disp[fi == k]))]
              for k in range(n_segs)]
    return {
        "id": f"{session.id}__couchshift",
        "kind": "couch_shift",
        "saved_ranges": [[float(lo), float(hi)]
                         for lo, hi in (state_entry or {}).get("ranges", [])],
        "kim": {"t": _r4(t_disp), "lr": _r4(segs["lr"]),
                "si": _r4(segs["si"]), "ap": _r4(segs["ap"])},
        "file_index": [int(x) for x in fi],
        "shifts": [[round(float(s["lr"]), ROUND_DP),
                    round(float(s["si"]), ROUND_DP),
                    round(float(s["ap"]), ROUND_DP)] for s in shifts],
        "expected_steps": [[round(float(a), ROUND_DP) for a in row]
                           for row in expected],
        "segment_bounds": [[round(lo, ROUND_DP), round(hi, ROUND_DP)]
                           for lo, hi in bounds],
        "shift_markers": [round(float(m), ROUND_DP) for m in markers],
    }
