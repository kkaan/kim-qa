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
_ISO_RE = re.compile(rf"Isocent(?:er|re)\s*(?:\(cm\))?\s*,\s*{_COORDS}")


def parse_centroid_file(filepath):
    """
    Parses the centroid file to extract seed and isocenter coordinates.
    Returns a dictionary with extracted values and the calculated expected centroid.

    Supports multi-seed patient files ("Seed 1", "Seed 2", ...) and
    single-marker phantom/robot files ("Marker_GTV").
    """
    with open(filepath, 'r') as f:
        content = f.read()

    # Extract seed/marker coordinates in file order (one or more supported).
    seeds = [[float(x), float(y), float(z)]
             for x, y, z in _MARKER_RE.findall(content)]

    if len(seeds) < 1:
        raise ValueError(f"Need at least 1 seed/marker in centroid file, found {len(seeds)}.")

    # Extract Isocenter coordinates
    iso_match = _ISO_RE.search(content)
    if not iso_match:
        raise ValueError("Could not find Isocenter coordinates in the centroid file.")

    isocenter = [float(iso_match.group(1)), float(iso_match.group(2)), float(iso_match.group(3))]

    # Calculate Average Marker Position (Centroid of seeds)
    avg_marker = np.mean(seeds, axis=0)

    # cm->mm scaling + MATLAB Staticloc.m axis swap (see kim_qa.coords)
    final_expected_centroid = expected_centroid_from_iso(avg_marker, isocenter)

    return {
        'seeds': seeds,
        'isocenter': isocenter,
        'expected_centroid': final_expected_centroid
    }
