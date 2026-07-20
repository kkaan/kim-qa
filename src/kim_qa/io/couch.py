"""Parse couchShifts.txt into per-transition AP/SI/LR shifts (mm).

This is the single canonical couch-shift parser. The Elekta/Varian vendor
AP-sign option lives here and nowhere else.
"""


def parse_couch_shifts(filepath, vendor="Elekta"):
    """
    Parses couchShifts.txt to extract VRT, LNG, LAT shifts.
    Returns a list of shifts in mm.

    vendor: "Elekta" (default) or "Varian". Varian negates the vertical->AP
    couch shift (Varian Truebeam/TreatmentInt.m:139 uses -diff(vrt)); SI and LR
    are identical across vendors. Default preserves historical Elekta behaviour.
    """
    ap_sign = -1.0 if str(vendor).lower() == "varian" else 1.0
    shifts = []
    try:
        with open(filepath, 'r') as f:
            # Skip header
            next(f)
            # Read lines
            # Format: VRT, LNG, LAT
            # Example: -15.80, 125.50, -0.30

            vrt_vals = []
            lng_vals = []
            lat_vals = []

            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    vrt_vals.append(float(parts[0]))
                    lng_vals.append(float(parts[1]))
                    lat_vals.append(float(parts[2]))

            # Calculate diffs and convert to mm (x10)
            # MATLAB: shiftsAP = diff(vrt) * 10;

            for i in range(len(vrt_vals) - 1):
                shift = {
                    'ap': (vrt_vals[i+1] - vrt_vals[i]) * 10 * ap_sign,
                    'si': (lng_vals[i+1] - lng_vals[i]) * 10,
                    'lr': (lat_vals[i+1] - lat_vals[i]) * 10
                }
                shifts.append(shift)

    except Exception as e:
        print(f"Error parsing couch shifts: {e}")

    return shifts
