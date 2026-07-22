"""Readers for KIM MarkerLocations_CouchShift_*.txt trajectory logs.

The non-GA header has 16 names but data rows have 17 fields (embedded comma in
the Filename column), so columns are read BY POSITION: cols 1..4 = time, AP,
LR, SI. Continuation files (_1, _2, ...) typically have no header row; presence
is sniffed per file (first line starting with "Frame").

The GA variant mirrors the same rows with a different layout (real files:
Frame No, Time (sec), Gantry, Marker_0_AP/LR/SI, ...); its Filename has no
embedded comma, so the Gantry column is resolved BY NAME from the first
file's header and that index is reused for headerless continuation files.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

KIM_FILENAME = "MarkerLocations_CouchShift_0.txt"
_SEG_RE = re.compile(r"^MarkerLocations_CouchShift_(\d+)\.txt$")
_GA_RE = re.compile(r"^MarkerLocationsGA_CouchShift_(\d+)\.txt$")
_MARKER_COL_RE = re.compile(r"^Marker_(\d+)_(AP|LR|SI)$")


def _marker_columns(path: Path):
    """{marker: {"AP": col, "LR": col, "SI": col}} resolved by name from the
    header, or None when the file is headerless or names no complete
    Marker_<n>_AP/LR/SI triple (older logs label the single marker's columns
    "AP (mm)", ...). Safe despite the embedded-comma Filename quirk: the
    marker columns sit left of Filename, so header and data indices agree."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        header = fh.readline()
    if not header.lstrip().startswith("Frame"):
        return None
    names = [c.strip() for c in header.split(",")]
    cols = {}
    for i, name in enumerate(names):
        m = _MARKER_COL_RE.match(name)
        if m:
            cols.setdefault(int(m.group(1)), {})[m.group(2)] = i
    complete = {k: v for k, v in cols.items() if len(v) == 3}
    return complete or None


def _has_header(path: Path) -> bool:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.readline().lstrip().startswith("Frame")


def _read_positional(path: Path, usecols):
    return pd.read_csv(
        path, skipinitialspace=True, header=None,
        skiprows=1 if _has_header(path) else 0, usecols=usecols,
    )


def _numbered_files(folder: Path, pattern: re.Pattern) -> list[Path]:
    items = []
    for p in folder.iterdir():
        m = pattern.match(p.name)
        if m:
            items.append((int(m.group(1)), p))
    items.sort()
    return [p for _, p in items]


def read_kim_segments(folder: Path) -> dict:
    """All MarkerLocations_CouchShift_*.txt in numeric order, concatenated.

    Multi-marker files (complete Marker_0/1/2 AP/LR/SI column triples in the
    first file's header) are averaged into a single centroid trajectory, the
    same reduction the MATLAB scripts applied; the column indices are reused
    for headerless continuation files. Headers without Marker triples fall
    back to the positional layout (cols 1..4 = time, AP, LR, SI).

    Returns dict of numpy arrays: t, lr, si, ap (raw, uncorrected, real
    timebase), int array file_index, and int n_markers.
    """
    files = _numbered_files(folder, _SEG_RE)
    if not files:
        raise FileNotFoundError(f"No {KIM_FILENAME[:-5]}*.txt in {folder}")
    markers = _marker_columns(files[0])
    t, lr, si, ap, fi = [], [], [], [], []
    for k, fp in enumerate(files):
        if markers is None:
            df = _read_positional(fp, usecols=[1, 2, 3, 4])
            df.columns = ["time", "ap", "lr", "si"]
            t.append(df["time"].to_numpy(float))
            ap.append(df["ap"].to_numpy(float))
            lr.append(df["lr"].to_numpy(float))
            si.append(df["si"].to_numpy(float))
        else:
            axis_cols = {axis: [m[axis] for m in markers.values()]
                         for axis in ("AP", "LR", "SI")}
            usecols = sorted({1, *(c for cs in axis_cols.values() for c in cs)})
            df = _read_positional(fp, usecols=usecols)
            t.append(df[1].to_numpy(float))
            for axis, dest in (("AP", ap), ("LR", lr), ("SI", si)):
                dest.append(np.mean(
                    [df[c].to_numpy(float) for c in axis_cols[axis]], axis=0))
        fi.append(np.full(len(df), k, dtype=int))
    return {
        "t": np.concatenate(t), "lr": np.concatenate(lr),
        "si": np.concatenate(si), "ap": np.concatenate(ap),
        "file_index": np.concatenate(fi),
        "n_markers": len(markers) if markers else 1,
    }


def _gantry_col_index(path: Path):
    """Index of the 'Gantry' column in a GA file's header, or None."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        header = fh.readline()
    if not header.lstrip().startswith("Frame"):
        return None
    names = [c.strip() for c in header.split(",")]
    return names.index("Gantry") if "Gantry" in names else None


def read_gantry_segments(folder: Path, expected_len: int):
    """Concatenated Gantry column across GA files, or None.

    The column index is resolved by name from the first GA file's header
    (real files carry Gantry at a different position than the non-GA layout)
    and reused for headerless continuation files. None when there are no GA
    files, the header lacks a Gantry column, or the total row count does not
    match expected_len (so a partial GA set never silently misaligns hover
    data).
    """
    files = _numbered_files(folder, _GA_RE)
    if not files:
        return None
    col = _gantry_col_index(files[0])
    if col is None:
        return None
    out = []
    for fp in files:
        df = _read_positional(fp, usecols=[col])
        out.append(df[col].to_numpy(float))
    g = np.concatenate(out)
    return g if len(g) == expected_len else None
