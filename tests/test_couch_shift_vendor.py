"""Vendor (Elekta/Varian) AP-sign behaviour + dict-based couch-shift correction.

Ground truth: Varian negates the vertical->AP couch shift relative to Elekta
(see Elekta/TreatmentInt.m:139 vs Varian Truebeam/TreatmentInt.m:139).
SI (LNG) and LR (LAT) are identical across vendors.

Run as a script:  python tests/test_couch_shift_vendor.py
"""
import os
import sys
import tempfile

import numpy as np

from kim_qa.io.couch import parse_couch_shifts
from kim_qa.interrupt import apply_couch_shifts

# Two couch positions (VRT, LNG, LAT) in cm; one shift between them.
# diffs: VRT +2 -> AP 20 mm, LNG +3 -> SI 30 mm, LAT +0.5 -> LR 5 mm
COUCH_TXT = "VRT (cm), LNG (cm), LAT (cm)\n10.0, 20.0, 5.0\n12.0, 23.0, 5.5\n"


def _write_temp():
    fd, path = tempfile.mkstemp(suffix="_couchShifts.txt")
    with os.fdopen(fd, "w") as fh:
        fh.write(COUCH_TXT)
    return path


def test_vendor_ap_sign():
    """AP flips sign for Varian; SI/LR unchanged; default == Elekta."""
    path = _write_temp()
    try:
        elekta = parse_couch_shifts(path, vendor="Elekta")[0]
        varian = parse_couch_shifts(path, vendor="Varian")[0]
        default = parse_couch_shifts(path)[0]

        assert elekta["ap"] == 20.0, elekta
        assert varian["ap"] == -20.0, varian
        assert default["ap"] == 20.0, "default must preserve Elekta behaviour"
        assert elekta["si"] == varian["si"] == 30.0
        assert elekta["lr"] == varian["lr"] == 5.0
    finally:
        os.remove(path)


def test_apply_couch_shifts_dict():
    """apply_couch_shifts consumes dict shifts and subtracts cumulative shift."""
    path = _write_temp()
    try:
        shifts = parse_couch_shifts(path)            # one shift: ap20 si30 lr5
        # Two segments: file 0 (pre-shift) and file 1 (post-shift).
        lr = np.array([0.0, 0.0])
        si = np.array([0.0, 0.0])
        ap = np.array([0.0, 0.0])
        file_index = np.array([0, 1])
        lr_c, si_c, ap_c = apply_couch_shifts(lr, si, ap, file_index, shifts)
        # Segment 0 unchanged; segment 1 has the applied shift removed.
        assert lr_c.tolist() == [0.0, -5.0], lr_c
        assert si_c.tolist() == [0.0, -30.0], si_c
        assert ap_c.tolist() == [0.0, -20.0], ap_c
    finally:
        os.remove(path)


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL  {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
    sys.exit(1 if failures else 0)
