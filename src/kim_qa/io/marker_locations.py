"""Readers for KIM MarkerLocations(GA)_CouchShift_*.txt trajectory logs.

The GA and non-GA variants carry IDENTICAL marker rows (verified to full
precision on real Bluey data); GA adds the Gantry column and a comma-free
Filename, the non-GA variant carries tracking diagnostics and a Filename with
an embedded comma (16 header names vs 17 data fields).

The GA files are therefore the canonical position source: marker columns
(Marker_<n>_AP/LR/SI) and Gantry are resolved BY NAME from the first file's
header and those indices are reused for headerless continuation files
(_1, _2, ...; header presence is sniffed per file). When GA files are absent
or their first file has no parsable header, the reader falls back to the
non-GA files: by name when the header carries Marker triples, otherwise BY
POSITION (cols 1..4 = time, AP, LR, SI — safe despite the embedded comma
because those columns sit left of Filename).
"""
import io
import re
from pathlib import Path

import numpy as np
import pandas as pd

KIM_FILENAME = "MarkerLocationsGA_CouchShift_0.txt"
FALLBACK_KIM_FILENAME = "MarkerLocations_CouchShift_0.txt"
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


# Once the run passes 1000 s, KIM writes the Time field with thousands
# separators ("1,028.870") into a comma-delimited file, so the row carries an
# extra field and EVERY column after Time shifts right by one — corrupting the
# marker positions, not just the clock. Anchored on the row start so only the
# second field (Time, following the integer Frame No) is ever rewritten: the
# unanchored form would also match a coordinate like ",130.466" in a log
# written without spaces after its commas.
_TIME_THOUSANDS_RE = re.compile(r"^(\s*\d+,[ \t]*)(\d{1,3}(?:,\d{3})+)", re.M)


def _read_positional(path: Path, usecols):
    text = path.read_text(encoding="utf-8", errors="replace")
    text = _TIME_THOUSANDS_RE.sub(
        lambda m: m.group(1) + m.group(2).replace(",", ""), text)
    return pd.read_csv(
        io.StringIO(text), skipinitialspace=True, header=None,
        skiprows=1 if _has_header(path) else 0, usecols=usecols,
    )


def _rebase_restarts(t: np.ndarray) -> tuple[np.ndarray, int]:
    """Make a concatenated timebase monotonic, returning (t, n_restarts).

    One CouchShift file can hold several kV acquisitions (the .his series
    restarts at 00001); each is clocked from its own origin, so the raw Time
    column jumps backwards and can go negative. Callers derive the run's span
    from t[0]/t[-1], which a backwards jump collapses — silently dropping
    samples from the metrics, or inverting the span entirely. Each restart is
    therefore re-based to continue one median sample step after the previous
    acquisition. Spacing WITHIN an acquisition is real and preserved exactly;
    the gap between them is not recoverable from the log, so it is nominal.
    """
    t = np.asarray(t, float)
    if t.size < 2:
        return t, 0
    steps = np.diff(t)
    forward = steps[steps > 0]
    step = float(np.median(forward)) if forward.size else 1.0
    out = t.copy()
    shift = 0.0
    restarts = 0
    for i in range(1, t.size):
        if t[i] < t[i - 1]:
            shift = out[i - 1] + step - t[i]
            restarts += 1
        out[i] = t[i] + shift
    return out, restarts


def _read_one_file(path: Path, markers) -> dict:
    """One log file's time and per-axis centroid arrays. With named marker
    columns the complete Marker_<n> triples are averaged into a centroid;
    without them the positional layout (cols 1..4 = time, AP, LR, SI) is
    read as a single marker."""
    if markers is None:
        df = _read_positional(path, usecols=[1, 2, 3, 4])
        df.columns = ["t", "ap", "lr", "si"]
        return {k: df[k].to_numpy(float) for k in ("t", "ap", "lr", "si")}
    axis_cols = {axis: [m[axis] for m in markers.values()]
                 for axis in ("AP", "LR", "SI")}
    usecols = sorted({1, *(c for cs in axis_cols.values() for c in cs)})
    df = _read_positional(path, usecols=usecols)
    out = {"t": df[1].to_numpy(float)}
    for axis in ("AP", "LR", "SI"):
        out[axis.lower()] = np.mean(
            [df[c].to_numpy(float) for c in axis_cols[axis]], axis=0)
    return out


def _numbered_files(folder: Path, pattern: re.Pattern) -> list[Path]:
    items = []
    for p in folder.iterdir():
        m = pattern.match(p.name)
        if m:
            items.append((int(m.group(1)), p))
    items.sort()
    return [p for _, p in items]


def read_kim_segments(folder: Path) -> dict:
    """All marker-log segments in numeric order, concatenated.

    GA files are the canonical source (marker columns resolved by name from
    the first file's header); non-GA files are the fallback when GA files are
    absent or headerless. Multi-marker files (complete Marker_0/1/2 AP/LR/SI
    column triples) are averaged into a single centroid trajectory, the same
    reduction the MATLAB scripts applied; the column indices are reused for
    headerless continuation files.

    Two PRIME patient-export quirks are repaired on the way in, both of which
    corrupt data silently rather than raising: the thousands separator KIM
    writes into the Time field past 1000 s (which shifts every later column
    right by one), and a clock re-referenced mid-file when one CouchShift file
    holds several kV acquisitions (see _rebase_restarts).

    Returns dict of numpy arrays: t, lr, si, ap (uncorrected positions on the
    real timebase, monotonic), int array file_index, int n_markers, and
    int time_restarts (how many clock re-references were re-based, 0 for a
    well-formed log).
    """
    files = _numbered_files(folder, _GA_RE)
    markers = _marker_columns(files[0]) if files else None
    if markers is None:
        files = _numbered_files(folder, _SEG_RE)
        if not files:
            raise FileNotFoundError(
                f"No MarkerLocations(GA)_CouchShift_*.txt in {folder}")
        markers = _marker_columns(files[0])
    t, lr, si, ap, fi = [], [], [], [], []
    for k, fp in enumerate(files):
        seg = _read_one_file(fp, markers)
        t.append(seg["t"])
        ap.append(seg["ap"])
        lr.append(seg["lr"])
        si.append(seg["si"])
        fi.append(np.full(len(seg["t"]), k, dtype=int))
    times, restarts = _rebase_restarts(np.concatenate(t))
    return {
        "t": times, "lr": np.concatenate(lr),
        "si": np.concatenate(si), "ap": np.concatenate(ap),
        "file_index": np.concatenate(fi),
        "n_markers": len(markers) if markers else 1,
        "time_restarts": restarts,
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
