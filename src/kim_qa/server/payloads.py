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


def _offline_label(name: str) -> str:
    """Legend label for an offline overlay folder: drop the leading 'kim-log'
    prefix (kim-log-pdf480 -> pdf480), falling back to the raw folder name."""
    lo = name.lower()
    for pre in ("kim-log-", "kim-log_", "kim-log"):
        if lo.startswith(pre):
            return name[len(pre):].strip(" -_") or name
    return name


def build_offline_overlays(session: Session, cent: dict, shifts: list,
                           state_entry: dict | None = None) -> list:
    """One entry per nested kim-log* folder: its trajectory centroid-corrected
    and couch-shift-corrected with the SAME expected offset and (session-level)
    shifts as the primary online trace. Each overlay carries its own saved time
    `offset` (seconds, keyed in state by folder name) or None to follow the
    primary run's offset — the offline replay has an independent timebase."""
    saved_offsets = (state_entry or {}).get("offline_offsets") or {}
    out = []
    for d in session.offline_dirs:
        try:
            segs = read_kim_segments(d)
        except Exception:  # noqa: BLE001 - skip an unreadable overlay folder
            continue
        lr = segs["lr"] - cent["lr"]
        si = segs["si"] - cent["si"]
        ap = segs["ap"] - cent["ap"]
        if shifts:
            lr, si, ap = apply_couch_shifts(lr, si, ap, segs["file_index"], shifts)
        off = saved_offsets.get(d.name)
        entry = {"label": _offline_label(d.name), "folder": d.name,
                 "t": _r4(segs["t"]), "lr": _r4(lr), "si": _r4(si), "ap": _r4(ap),
                 "file_index": [int(x) for x in segs["file_index"]],
                 "offset": round(float(off), ROUND_DP)
                 if isinstance(off, (int, float)) else None}
        gantry = read_gantry_segments(d, expected_len=len(segs["t"]))
        if gantry is not None:
            entry["gantry"] = _r4(gantry)
        out.append(entry)
    return out


def build_manifest_entries(sessions, state: dict) -> list[dict]:
    """Per-session manifest dicts (the fields the overlay widget reads from the
    manifest rather than the payload: y_range, hex_override, offset_origin, saved
    offset/ranges, and session flags). Shared by the live /api/manifest route and
    the static deck exporter so the two contracts never drift.

    `state` is the loaded _overlay_state.json; `sessions` an iterable of Session.
    """
    entries = []
    for sess in sessions:
        entry = state.get(sess.id, {}) if isinstance(state, dict) else {}
        if not isinstance(entry, dict):
            entry = {}
        entries.append({
            "id": sess.id,
            "kind": sess.kind,
            "hex_file": sess.hex_file.name if sess.hex_file else None,
            "centroid_file": (sess.centroid_file.name
                              if sess.centroid_file else None),
            "has_frames": sess.has_frames,
            "has_couch_shifts": sess.has_couch_shifts,
            "saved_offset": entry.get("offset"),
            "saved_ranges": entry.get("ranges", []),
            "offset_origin": entry.get("offset_origin"),
            "y_range": entry.get("y_range"),
            "hex_override": entry.get("hex_override"),
            "error": sess.error,
        })
    return entries


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
    xr = (state_entry or {}).get("x_range")
    saved_x_range = ([round(float(xr[0]), ROUND_DP), round(float(xr[1]), ROUND_DP)]
                     if isinstance(xr, (list, tuple)) and len(xr) == 2 else None)
    kim = {"t": _r4(arrays["t"]), "lr": _r4(arrays["lr"]),
           "si": _r4(arrays["si"]), "ap": _r4(arrays["ap"])}
    if arrays["gantry"] is not None:
        kim["gantry"] = _r4(arrays["gantry"])
    payload = {
        "id": session.id,
        "kind": session.kind,
        "saved_offset": round(float(offset), ROUND_DP),
        "saved_ranges": ranges,
        "saved_x_range": saved_x_range,
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
    overlays = build_offline_overlays(session, arrays["centroid"], arrays["shifts"],
                                      state_entry)
    if overlays:
        payload["kim_offline"] = overlays
    return payload
