"""Parse KIM centroid (patient) files: seed + isocenter coordinates."""
import re

import numpy as np

from kim_qa.coords import expected_centroid_from_iso

# A coordinate triple with tolerant whitespace around '=' and the separating
# commas, e.g. "X=  1.0, Y=  1.0, Z=  1.0" or "X=0.0 , Y=0.0 , Z=0.0".
_COORDS = r"X=\s*([-\d.]+)\s*,\s*Y=\s*([-\d.]+)\s*,\s*Z=\s*([-\d.]+)"

# Marker/seed lines. Patient files label fiducials "Seed 1", "Seed 2", ...;
# phantom/robot files use a single "Marker_<label>" (e.g. "Marker_GTV").
_MARKER_RE = re.compile(rf"(?:Seed\s*\d+|Marker_\w+)\s*,\s*{_COORDS}")

# Isocenter line. Tolerates the "Isocenter"/"Isocentre" spelling and the
# optional "(cm)" unit suffix (present in patient files, absent in phantom files).
# KIM's own export labels this line "Centroid (cm)" — a different name for the
# same quantity: Staticloc.m:31-33 subtracts it from the seed mean, which is the
# isocentre's role here.
_ISO_RE = re.compile(
    rf"(?:Isocent(?:er|re)|Centroid)\s*(?:\(cm\))?\s*,\s*{_COORDS}")

# A bare "x y z" row, whitespace-separated. Commas are deliberately not
# tolerated, so comma-delimited data (couchShifts.txt, robot traces) cannot
# masquerade as a centroid file.
_BARE_ROW_RE = re.compile(r"^\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*$")


def _parse_bare_numeric(content):
    """Label-free variant hand-made for the MATLAB QA codes: one "x y z" row
    per seed with the isocentre last (Elekta/Staticloc.m:23-37 reads it with
    fscanf and treats the final row as the isocentre).

    Returns (seeds, isocenter), or None when the file is not exclusively
    3-float rows — requiring *every* line to match keeps 7-column robot traces
    out, which a flat float count would let through whenever it divides by 3.
    """
    rows = []
    for line in content.splitlines():
        if not line.strip():
            continue
        m = _BARE_ROW_RE.match(line)
        if m is None:
            return None
        try:
            rows.append([float(v) for v in m.groups()])
        except ValueError:            # e.g. a lone "-" or ".." token
            return None
    if len(rows) < 2:                 # need at least one seed plus the isocentre
        return None
    return rows[:-1], rows[-1]


def parse_centroid_file(filepath):
    """
    Parses the centroid file to extract seed and isocenter coordinates.
    Returns a dictionary with extracted values and the calculated expected centroid.

    Supports multi-seed patient files ("Seed 1", "Seed 2", ...), single-marker
    phantom/robot files ("Marker_GTV"), and the label-free numeric variant the
    MATLAB QA codes were fed.
    """
    with open(filepath, 'r') as f:
        content = f.read()

    # Extract seed/marker coordinates in file order (one or more supported).
    seeds = [[float(x), float(y), float(z)]
             for x, y, z in _MARKER_RE.findall(content)]
    iso_match = _ISO_RE.search(content)

    if not seeds and iso_match is None:
        bare = _parse_bare_numeric(content)
        if bare is not None:
            seeds, isocenter = bare
            return _result(seeds, isocenter)

    if len(seeds) < 1:
        raise ValueError(f"Need at least 1 seed/marker in centroid file, found {len(seeds)}.")

    if not iso_match:
        raise ValueError("Could not find Isocenter coordinates in the centroid file.")

    isocenter = [float(iso_match.group(1)), float(iso_match.group(2)), float(iso_match.group(3))]
    return _result(seeds, isocenter)


def _result(seeds, isocenter):
    """Shared tail: seed mean -> isocentre-relative expected centroid."""
    # Calculate Average Marker Position (Centroid of seeds)
    avg_marker = np.mean(seeds, axis=0)

    # cm->mm scaling + MATLAB Staticloc.m axis swap (see kim_qa.coords)
    final_expected_centroid = expected_centroid_from_iso(avg_marker, isocenter)

    return {
        'seeds': seeds,
        'isocenter': isocenter,
        'expected_centroid': final_expected_centroid
    }
